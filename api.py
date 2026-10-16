
import asyncio
import json
import queue
import threading
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException, UploadFile, File
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

from rag.ingest import ingest_pdf_bytes


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


# =========================================================
# SHARED SETTINGS
# =========================================================

# Maximum PDF upload size: 20 MB
MAX_PDF_SIZE = 20 * 1024 * 1024

# Keep agent execution sequential because it uses shared state.
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
# PDF UPLOAD ENDPOINT
# =========================================================

@app.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    """
    Read an uploaded PDF in memory and index its text and embeddings
    in ChromaDB. The original PDF is not saved to disk.
    """

    try:
        filename = file.filename or ""

        # Validate file extension.
        if not filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=400,
                detail="Only PDF files are supported.",
            )

        # Read at most 20 MB plus one byte to detect oversized uploads.
        pdf_bytes = await file.read(MAX_PDF_SIZE + 1)

        if not pdf_bytes:
            raise HTTPException(
                status_code=400,
                detail="The uploaded PDF is empty.",
            )

        if len(pdf_bytes) > MAX_PDF_SIZE:
            raise HTTPException(
                status_code=413,
                detail="PDF is too large. Maximum upload size is 20 MB.",
            )

        # Basic check that the file looks like a PDF.
        if b"%PDF-" not in pdf_bytes[:1024]:
            raise HTTPException(
                status_code=400,
                detail="The uploaded file does not appear to be a valid PDF.",
            )

        # Run CPU-intensive embedding work outside the async event loop.
        # The lock avoids overlapping ingestion with agent execution.
        def ingest_task():
            with agent_lock:
                return ingest_pdf_bytes(
                    pdf_bytes=pdf_bytes,
                    filename=filename,
                )

        result = await asyncio.to_thread(ingest_task)

        return result

    except HTTPException:
        raise

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    except Exception as error:
        print(f"PDF upload failed: {error}")

        raise HTTPException(
            status_code=500,
            detail=(
                "PDF processing failed. Check the backend terminal "
                "for details."
            ),
        ) from error

    finally:
        await file.close()


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

    # Support frontend requests that do not send a conversation ID.
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

            yield (
                f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
            )

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
