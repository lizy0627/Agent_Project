from typing import Any

from backend.app.tools.base import BaseTool, ToolResult
from backend.app.tools.registry import (
    API_KEY_MISSING,
    DEFAULT_RETRY_BACKOFF_SECONDS,
    EMPTY_RESULT,
    HTTP_ERROR,
    INVALID_ARGUMENTS,
    MCP_SERVER_UNAVAILABLE,
    NETWORK_ERROR,
    PARSE_ERROR,
    RATE_LIMIT,
    RETRYABLE_ERROR_CODES,
    TOOL_EXECUTION_ERROR,
    TOOL_NOT_FOUND,
    TOOL_TIMEOUT,
    ToolRegistry,
)


class ToolManager(ToolRegistry):
    """Backward-compatible wrapper around ToolRegistry."""

    def get(self, name: str) -> BaseTool | None:
        return self.get_tool(name)

    def call(self, name: str, max_retries: int = 1, **kwargs: Any) -> ToolResult:
        return self.run_tool(name, kwargs, max_retries=max_retries)

    def list_tool_names(self) -> list[str]:
        return sorted(self._tools)


__all__ = [
    "API_KEY_MISSING",
    "DEFAULT_RETRY_BACKOFF_SECONDS",
    "EMPTY_RESULT",
    "HTTP_ERROR",
    "INVALID_ARGUMENTS",
    "MCP_SERVER_UNAVAILABLE",
    "NETWORK_ERROR",
    "PARSE_ERROR",
    "RATE_LIMIT",
    "RETRYABLE_ERROR_CODES",
    "TOOL_EXECUTION_ERROR",
    "TOOL_NOT_FOUND",
    "TOOL_TIMEOUT",
    "ToolManager",
    "ToolRegistry",
]
