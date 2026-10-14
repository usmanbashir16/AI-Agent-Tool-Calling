
import asyncio
import json
import queue
import threading
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from main import (
    initialize_database,
    run_agent,
    sync_sqlite_memories,
    sync_sqlite_conversations,
)

app = FastAPI(title="AI Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Only one agent request at a time because the current agent
# uses a shared global conversation_history.
agent_lock = threading.Lock()
executor = ThreadPoolExecutor(max_workers=1)


class ChatRequest(BaseModel):
    message: str


@app.on_event("startup")
def startup():
    initialize_database()
    sync_sqlite_memories()
    sync_sqlite_conversations()


def format_sse(event_data):
    return f"data: {json.dumps(event_data, ensure_ascii=False, default=str)}\n\n"


@app.get("/health")
def health():
    return {"status": "ok", "message": "AI Agent API is running"}


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    message = request.message.strip()

    if not message:
        return {"error": "Message cannot be empty."}

    events = queue.Queue()
    finished = threading.Event()

    def send_activity(activity):
        events.put(activity)

    def run_agent_task():
        try:
            with agent_lock:
                reply = run_agent(
                    message,
                    activity_callback=send_activity,
                )

            events.put({
                "type": "answer",
                "message": reply or "",
            })

        except Exception as error:
            events.put({
                "type": "error",
                "message": str(error),
            })

        finally:
            finished.set()

    async def event_generator():
        loop = asyncio.get_running_loop()
        task = loop.run_in_executor(executor, run_agent_task)

        try:
            while not finished.is_set() or not events.empty():
                try:
                    event = events.get_nowait()
                    yield format_sse(event)
                except queue.Empty:
                    yield ": keep-alive\n\n"
                    await asyncio.sleep(0.2)

            # Send any final queued events.
            while not events.empty():
                yield format_sse(events.get_nowait())

            await task

            yield format_sse({"type": "done", "message": "Completed"})

        except asyncio.CancelledError:
            # The synchronous agent may finish in the background if
            # the browser disconnects. Do not modify its shared history.
            raise

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )