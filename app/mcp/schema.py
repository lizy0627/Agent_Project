from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class MCPServerConfig(BaseModel):
    """Configuration for one MCP server loaded from servers.json."""

    key: str = ""
    name: str
    transport: Literal["http", "sse"] = "http"
    url: str | None = None
    enabled: bool = True
    keywords: list[str] = Field(default_factory=list)
    description: str = ""
    timeout_seconds: int | None = None
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    category: str | None = None

    @field_validator("transport", mode="before")
    @classmethod
    def normalize_transport(cls, value: Any) -> str:
        return str(value or "http").strip().lower()


class MCPToolInfo(BaseModel):
    """Tool metadata cached per MCP server."""

    server_name: str
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)


class MCPCallRequest(BaseModel):
    server_name: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class MCPCallResult(BaseModel):
    success: bool
    server_name: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    data: Any = None
    error: str = ""
    elapsed_ms: float = 0
