
import asyncio
import json
import queue
import threading
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from main import (
    initialize_database,
    run_agent,
    create_conversation,
    list_conversations,
    get_conversation_messages,
    sync_sqlite_memories,
    sync_sqlite_conversations,
)


# =========================================================
# FASTAPI CONFIGURATION
# =========================================================

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


# Keep agent execution sequential because each request has its
# own loaded history, while other existing tools may use shared state.
agent_lock = threading.Lock()
executor = ThreadPoolExecutor(max_workers=1)


# =========================================================
# REQUEST MODELS
# =========================================================

class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


class CreateConversationRequest(BaseModel):
    title: str = "New conversation"


# =========================================================
# STARTUP
# =========================================================

@app.on_event("startup")
def startup_event():
    initialize_database()
    sync_sqlite_memories()
    sync_sqlite_conversations()
    print("AI Agent API started successfully.")


# =========================================================
# HELPERS
# =========================================================

def conversation_exists(conversation_id: str) -> bool:
    """Check whether a conversation ID exists."""
    return any(
        item["id"] == conversation_id
        for item in list_conversations()
    )


# =========================================================
# HEALTH CHECK
# =========================================================

@app.get("/health")
def health_check():
    return {"status": "API is running"}


# =========================================================
# CONVERSATION ENDPOINTS
# =========================================================

@app.get("/conversations")
def get_conversations():
    """List saved conversations for the frontend sidebar."""
    return {"conversations": list_conversations()}


@app.post("/conversations")
def new_conversation(request: CreateConversationRequest):
    """Create and return a new conversation."""
    title = " ".join(request.title.split())[:60]
    if not title:
        title = "New conversation"

    conversation_id = create_conversation(title)

    return {
        "id": conversation_id,
        "title": title,
    }


@app.get("/conversations/{conversation_id}/messages")
def get_messages(conversation_id: str):
    """Load messages from one saved conversation."""
    if not conversation_exists(conversation_id):
        raise HTTPException(
            status_code=404,
            detail="Conversation not found.",
        )

    messages = get_conversation_messages(conversation_id)

    return {
        "conversation_id": conversation_id,
        "messages": messages,
    }


# =========================================================
# STREAMING CHAT ENDPOINT
# =========================================================

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Stream agent activity and the final answer using SSE."""

    message = request.message.strip()

    if not message:
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty.",
        )

    # Support older frontend requests that do not yet send an ID.
    if request.conversation_id:
        conversation_id = request.conversation_id

        if not conversation_exists(conversation_id):
            raise HTTPException(
                status_code=404,
                detail="Conversation not found.",
            )
    else:
        conversation_id = create_conversation()

    event_queue = queue.Queue()

    def send_activity(event_type, message, details=None):
        """Receive activity updates from run_agent()."""
        event_queue.put({
            "type": "activity",
            "activity_type": event_type,
            "message": message,
            "details": details or {},
        })

    def run_agent_task():
        try:
            with agent_lock:
                answer = run_agent(
                    message,
                    conversation_id=conversation_id,
                    activity_callback=send_activity,
                )

            event_queue.put({
                "type": "answer",
                "answer": answer,
                "conversation_id": conversation_id,
            })

        except Exception as error:
            print(f"Agent request failed: {error}")

            event_queue.put({
                "type": "error",
                "error": str(error),
                "conversation_id": conversation_id,
            })

        finally:
            event_queue.put({"type": "done"})

    executor.submit(run_agent_task)

    async def event_generator():
        loop = asyncio.get_running_loop()

        while True:
            event = await loop.run_in_executor(
                None,
                event_queue.get,
            )

            yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"

            if event.get("type") == "done":
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )