from typing import Any, Literal

from pydantic import BaseModel, Field


AgentMode = Literal["plan_execute", "react", "multi_agent"]


class ChatRequest(BaseModel):
    """Request body for the chat endpoint."""

    message: str = Field(..., min_length=1, max_length=4000, description="User message")
    # Compatibility field for older clients. Prefer agent_mode="multi_agent" for new requests.
    multi_agent: bool = Field(
        default=False,
        description=(
            "Deprecated compatibility flag. When true, it is equivalent to "
            'agent_mode="multi_agent".'
        ),
    )
    agent_mode: AgentMode = Field(
        default="plan_execute",
        description=(
            "Agent execution mode. Use plan_execute for planner/executor, react for ReAct, "
            "or multi_agent for ManagerAgent orchestration."
        ),
    )
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
    retryable: bool | None = None
    tool_name: str | None = None
    duration_ms: float | None = None


class AgentTraceStep(BaseModel):
    """One front-end renderable step in an agent request lifecycle."""

    step: str = Field(..., description="Stable step key, for example planner/tool_call/observation/final_answer")
    status: str = Field(..., description="Step status, for example running/success/failed/skipped")
    message: str | None = Field(default=None, description="Short human-readable step message")
    step_id: str | None = Field(default=None, description="Planner step id when available")
    description: str | None = Field(default=None, description="Planner step description when available")
    tool_name: str | None = Field(default=None, description="Tool name when this step calls a tool")
    tool_args: dict[str, Any] | None = Field(default=None, description="Tool arguments when available")
    tool_call: dict[str, Any] | None = Field(default=None, description="Structured tool call record")
    depends_on: list[str] | None = Field(default=None, description="Planner step dependencies")
    observation: Any | None = Field(default=None, description="Tool output or execution observation")
    duration_ms: float | None = Field(default=None, description="Step duration in milliseconds")
    error_code: str | None = Field(default=None, description="Stable error code when this step failed")
    retryable: bool | None = Field(default=None, description="Whether this failed step can be retried")
    request_id: str | None = Field(default=None, description="Request id associated with this trace step")
    metadata: dict[str, Any] | None = Field(default=None, description="Optional structured UI hints")


class ChatResponse(BaseModel):
    """Response body returned by the chat endpoint."""

    success: bool = True
    request_id: str = Field(..., description="Server-generated request id for tracing one chat request")
    reply: str
    model: str
    conversation_id: str
    multi_agent: bool = False
    agent_results: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Structured sub-agent outputs when multi-agent mode is enabled.",
    )
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
