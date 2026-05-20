from time import perf_counter
from typing import Any

from app.core.logger import get_logger
from app.core.safe_logging import safe_log_data
from app.tools.base import Tool, ToolResult


logger = get_logger(__name__)
TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
TOOL_TIMEOUT = "TOOL_TIMEOUT"
TOOL_EXECUTION_ERROR = "TOOL_EXECUTION_ERROR"
INVALID_ARGUMENTS = "INVALID_ARGUMENTS"
NETWORK_ERROR = "NETWORK_ERROR"
API_KEY_MISSING = "API_KEY_MISSING"
MCP_SERVER_UNAVAILABLE = "MCP_SERVER_UNAVAILABLE"


class ToolManager:
    """Register and execute local tools with consistent logging and errors."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool
        logger.info("Tool registered: name=%s", tool.name)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def call(self, name: str, **kwargs: Any) -> ToolResult:
        started_at = perf_counter()
        tool = self.get(name)
        if tool is None:
            duration_ms = self._elapsed_ms(started_at)
            result = ToolResult(
                name=name,
                success=False,
                error=f"Tool is not registered: {name}",
                duration_ms=duration_ms,
                error_code=TOOL_NOT_FOUND,
                error_message=f"Tool is not registered: {name}",
                retryable=False,
            )
            self._log_tool_finished(result)
            return result

        try:
            logger.info("Tool call started: name=%s args=%s", name, safe_log_data(kwargs))
            data = tool.run(**kwargs)
            result = self._build_success_result(name, data, self._elapsed_ms(started_at))
        except Exception as exc:
            result = self._build_error_result(
                name=name,
                error_message=str(exc),
                duration_ms=self._elapsed_ms(started_at),
                exc=exc,
            )
            logger.exception(
                "Tool call failed: tool_name=%s success=%s duration_ms=%s error_code=%s",
                result.name,
                result.success,
                result.duration_ms,
                result.error_code,
            )

        self._log_tool_finished(result)
        return result

    def list_tools(self) -> list[str]:
        return sorted(self._tools)

    def _elapsed_ms(self, started_at: float) -> float:
        return round((perf_counter() - started_at) * 1000, 2)

    def _build_success_result(self, name: str, data: Any, duration_ms: float) -> ToolResult:
        if self._result_indicates_failure(data):
            error_message = self._extract_result_error(data)
            error_code, retryable = self._classify_error(name, error_message)
            return ToolResult(
                name=name,
                success=False,
                result=data,
                error=error_message,
                duration_ms=duration_ms,
                error_code=error_code,
                error_message=error_message,
                retryable=retryable,
            )

        return ToolResult(
            name=name,
            success=True,
            result=data,
            duration_ms=duration_ms,
        )

    def _build_error_result(
        self,
        name: str,
        error_message: str,
        duration_ms: float,
        exc: Exception,
    ) -> ToolResult:
        error_code, retryable = self._classify_error(name, error_message, exc=exc)
        return ToolResult(
            name=name,
            success=False,
            error=error_message,
            duration_ms=duration_ms,
            error_code=error_code,
            error_message=error_message,
            retryable=retryable,
        )

    def _result_indicates_failure(self, data: Any) -> bool:
        return isinstance(data, dict) and data.get("success") is False

    def _extract_result_error(self, data: Any) -> str:
        if isinstance(data, dict):
            error = data.get("error") or data.get("error_message") or "Tool returned a failed result."
            return str(error)
        return "Tool returned a failed result."

    def _classify_error(
        self,
        name: str,
        error_message: str,
        exc: Exception | None = None,
    ) -> tuple[str, bool]:
        normalized_message = error_message.lower()
        if isinstance(exc, TimeoutError):
            return TOOL_TIMEOUT, True
        if self._looks_like_api_key_missing(normalized_message):
            return API_KEY_MISSING, False
        if "timed out" in normalized_message or "timeout" in normalized_message:
            return TOOL_TIMEOUT, True
        if self._looks_like_mcp_server_unavailable(name, normalized_message):
            return MCP_SERVER_UNAVAILABLE, True
        if isinstance(exc, ConnectionError) or self._looks_like_network_error(normalized_message):
            return NETWORK_ERROR, True
        if isinstance(exc, (ValueError, TypeError)):
            return INVALID_ARGUMENTS, False
        return TOOL_EXECUTION_ERROR, False

    def _looks_like_api_key_missing(self, message: str) -> bool:
        return (
            "api key" in message
            or "api_key" in message
            or "apikey" in message
        ) and any(marker in message for marker in ("missing", "not configured", "empty", "required"))

    def _looks_like_mcp_server_unavailable(self, name: str, message: str) -> bool:
        if name != "mcp_tool" and "mcp" not in message:
            return False
        unavailable_markers = (
            "not configured",
            "disabled",
            "unsupported",
            "unavailable",
            "unreachable",
            "not running",
            "server is running",
            "connection",
            "connect",
            "timed out",
            "timeout",
        )
        return any(marker in message for marker in unavailable_markers)

    def _looks_like_network_error(self, message: str) -> bool:
        return any(
            marker in message
            for marker in (
                "network",
                "connection",
                "connect",
                "unable to read",
                "unable to connect",
                "request failed",
                "http",
            )
        )

    def _log_tool_finished(self, result: ToolResult) -> None:
        logger.info(
            "Tool call finished: tool_name=%s success=%s duration_ms=%s error_code=%s",
            result.name,
            result.success,
            result.duration_ms,
            result.error_code,
        )
