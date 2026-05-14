from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request body for the chat endpoint."""

    message: str = Field(..., min_length=1, description="User message")
    system_prompt: str | None = Field(
        default=None,
        description="Optional system prompt for the agent",
    )
    conversation_id: str | None = Field(
        default=None,
        description="Optional conversation id for multi-turn chat",
    )


class ChatResponse(BaseModel):
    """Response body returned by the chat endpoint."""

    success: bool = True
    reply: str
    model: str
    conversation_id: str
    used_tool: bool = False
    tool_name: str | None = None
    tool_result: Any | None = None


class ErrorResponse(BaseModel):
    """Unified error response body."""

    success: bool = False
    error: str
