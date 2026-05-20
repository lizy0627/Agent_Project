from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request body for the chat endpoint."""

    message: str = Field(..., min_length=1, max_length=4000, description="User message")
    system_prompt: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional system prompt for the agent",
    )
    model: str | None = Field(
        default=None,
        max_length=100,
        description="Optional DashScope model name. Falls back to server default when omitted.",
    )
    conversation_id: str | None = Field(
        default=None,
        max_length=100,
        description="Optional conversation id for multi-turn chat",
    )
    max_context_rounds: int | None = Field(
        default=None,
        ge=0,
        le=30,
        description="Optional number of previous user/assistant rounds to include.",
    )


class ErrorDetail(BaseModel):
    """Structured error detail returned by API error responses."""

    code: str
    message: str
    retryable: bool = False


class ChatResponse(BaseModel):
    """Response body returned by the chat endpoint."""

    success: bool = True
    reply: str
    model: str
    conversation_id: str
    used_tool: bool = False
    tool_name: str | None = None
    tool_status: str | None = None
    tool_result: Any | None = None
    tool_error: str | None = None
    tool_duration_ms: float | None = None
    tool_error_code: str | None = None
    tool_error_message: str | None = None
    tool_retryable: bool | None = None
    tool_error_detail: ErrorDetail | None = None


class ConversationClearResponse(BaseModel):
    """Response body returned after clearing one conversation."""

    success: bool = True
    conversation_id: str
    message: str


class ConversationMessagesResponse(BaseModel):
    """Response body returned when reading one conversation history."""

    success: bool = True
    conversation_id: str
    messages: list[dict[str, str]]


class ErrorResponse(BaseModel):
    """Unified error response body."""

    success: bool = False
    error: ErrorDetail
    # Legacy-friendly fields for existing frontend/client code.
    message: str
    error_code: str
    error_message: str
    retryable: bool = False
