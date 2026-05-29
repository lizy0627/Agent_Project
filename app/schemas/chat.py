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


class AgentTraceStep(BaseModel):
    """One front-end renderable step in an agent request lifecycle."""

    step: str = Field(..., description="Stable step key, for example plan/tool_call/model_generate")
    status: str = Field(..., description="Step status, for example running/success/failed/skipped")
    message: str | None = Field(default=None, description="Short human-readable step message")
    tool_name: str | None = Field(default=None, description="Tool name when this step calls a tool")
    duration_ms: float | None = Field(default=None, description="Step duration in milliseconds")
    metadata: dict[str, Any] | None = Field(default=None, description="Optional structured UI hints")


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
    trace: list[AgentTraceStep] = Field(
        default_factory=list,
        description="Ordered agent execution trace for UI rendering and debugging.",
    )


class ConversationClearResponse(BaseModel):
    """Response body returned after clearing one conversation."""

    success: bool = True
    conversation_id: str
    message: str


class ConversationSummary(BaseModel):
    """One conversation item in the paginated list."""

    id: str
    user_id: str
    title: str
    last_message_summary: str
    message_count: int
    created_at: str
    updated_at: str


class ConversationListResponse(BaseModel):
    """Response body returned when reading the current user's conversations."""

    success: bool = True
    conversations: list[ConversationSummary]
    total: int
    limit: int
    offset: int
    has_more: bool


class ConversationMessagesResponse(BaseModel):
    """Response body returned when reading one conversation history."""

    success: bool = True
    conversation_id: str
    messages: list[dict[str, str]]
    total: int | None = None
    limit: int | None = None
    offset: int | None = None
    has_more: bool | None = None


class ErrorResponse(BaseModel):
    """Unified error response body."""

    success: bool = False
    error: ErrorDetail
    # Legacy-friendly fields for existing frontend/client code.
    message: str
    error_code: str
    error_message: str
    retryable: bool = False
