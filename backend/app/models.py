from pydantic import BaseModel, Field
from typing import Optional, Literal, Dict, Any, List

class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1, description="Unique session identifier")
    message: str = Field(..., min_length=1, description="User message content")
    system_prompt: Optional[str] = Field(None, description="Optional system instructions")

class MessageMetadata(BaseModel):
    source: Literal["LIVE_INFERENCE", "LLM_CACHE"]
    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int

class ChatResponse(BaseModel):
    session_id: str
    role: str = "assistant"
    content: str
    metadata: MessageMetadata

class MessageRecord(BaseModel):
    id: int
    session_id: str
    role: str
    content: str
    metadata: Optional[Dict[str, Any]] = None
    created_at: str

class HealthResponse(BaseModel):
    status: str
    configured_keys: int
    cache_status: str
