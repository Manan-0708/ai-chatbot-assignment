from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
from contextlib import asynccontextmanager

from .config import settings
from .database import init_db, get_session_messages, save_message
from .models import ChatRequest, ChatResponse, HealthResponse, MessageRecord
from .llm import execute_chat_completion, AllProvidersUnavailableException, cache_status

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the database automatically on startup
    init_db()
    yield

app = FastAPI(
    title="AI Chatbot API",
    description="Full-stack AI Chatbot backend with LiteLLM, failover, caching, and SQLite session history",
    version="1.0.0",
    lifespan=lifespan
)

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", response_model=HealthResponse)
def health():
    """Health check endpoint returning service status, key count, and cache status."""
    return HealthResponse(
        status="ok",
        configured_keys=len(settings.api_keys_list),
        cache_status=cache_status
    )

@app.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    x_simulate_failure: Optional[str] = Header(None, alias="X-Simulate-Failure")
):
    """
    Chat endpoint:
    - Maintains conversation history across turns.
    - Resolves via LiteLLM with automatic fallback and caching.
    - Simulates failures when X-Simulate-Failure is set and enabled.
    - If all providers fail, returns 503 and does not save the request.
    - Stores user and assistant messages in SQLite on success.
    """
    if not request.session_id.strip() or not request.message.strip():
        raise HTTPException(status_code=422, detail="session_id and message cannot be empty")

    # Fetch prior conversation history
    history = get_session_messages(request.session_id)

    # Build prompt messages for LiteLLM
    llm_messages = []
    if request.system_prompt and request.system_prompt.strip():
        llm_messages.append({"role": "system", "content": request.system_prompt.strip()})

    for msg in history:
        llm_messages.append({"role": msg["role"], "content": msg["content"]})

    llm_messages.append({"role": "user", "content": request.message})

    # Call LLM with fallback, caching, and failure simulation
    try:
        content, metadata = execute_chat_completion(
            messages=llm_messages,
            simulate_header=x_simulate_failure
        )
    except AllProvidersUnavailableException:
        # Crucial requirement: return 503 and do NOT save failed request in history
        raise HTTPException(status_code=503, detail="all providers unavailable")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM execution error: {str(e)}")

    # Only upon successful generation, store user and assistant messages in SQLite
    save_message(session_id=request.session_id, role="user", content=request.message, metadata=None)
    save_message(session_id=request.session_id, role="assistant", content=content, metadata=metadata)

    return ChatResponse(
        session_id=request.session_id,
        role="assistant",
        content=content,
        metadata=metadata
    )

@app.get("/sessions/{session_id}/messages", response_model=List[MessageRecord])
def get_messages(session_id: str):
    """Retrieve the complete chat history for a session in chronological order."""
    return get_session_messages(session_id)
