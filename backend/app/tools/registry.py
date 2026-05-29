import re
from time import perf_counter, sleep
from typing import Any

from backend.app.core.logger import get_logger
from backend.app.core.safe_logging import safe_log_data
from backend.app.tools.base import BaseTool, ToolResult


logger = get_logger(__name__)
TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
TOOL_TIMEOUT = "TOOL_TIMEOUT"
TOOL_EXECUTION_ERROR = "TOOL_EXECUTION_ERROR"
INVALID_ARGUMENTS = "INVALID_ARGUMENTS"
NETWORK_ERROR = "NETWORK_ERROR"
API_KEY_MISSING = "API_KEY_MISSING"
MCP_SERVER_UNAVAILABLE = "MCP_SERVER_UNAVAILABLE"
RATE_LIMIT = "RATE_LIMIT"
HTTP_ERROR = "HTTP_ERROR"
PARSE_ERROR = "PARSE_ERROR"
EMPTY_RESULT = "EMPTY_RESULT"
RETRYABLE_ERROR_CODES = {TOOL_TIMEOUT, NETWORK_ERROR, MCP_SERVER_UNAVAILABLE}
DEFAULT_RETRY_BACKOFF_SECONDS = 0.3


class ToolRegistry:
    """Register and execute tools through one normalized runtime."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._validate_tool(tool)
        self._tools[tool.name] = tool
        logger.info("Tool registered: name=%s", tool.name)

    def get_tool(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[dict[str, Any]]:
        return [self._tools[name].definition() for name in sorted(self._tools)]

    def run_tool(self, name: str, args: dict[str, Any] | None = None, max_retries: int = 1) -> ToolResult:
        started_at = perf_counter()
        tool = self.get_tool(name)
        if tool is None:
            result = ToolResult(
                name=name,
                success=False,
                error=f"Tool is not registered: {name}",
                duration_ms=self._elapsed_ms(started_at),
                error_code=TOOL_NOT_FOUND,
                error_message=f"Tool is not registered: {name}",
                retryable=False,
            )
            self._log_tool_finished(result)
            return result

        kwargs = args or {}
        retry_count = self._normalize_max_retries(max_retries)
        attempts = retry_count + 1
        result: ToolResult | None = None
        for attempt in range(1, attempts + 1):
            try:
                logger.info(
                    "Tool call started: name=%s attempt=%s args=%s",
                    name,
                    attempt,
                    safe_log_data(kwargs),
                )
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
                    "Tool call failed: tool_name=%s attempt=%s success=%s duration_ms=%s error_code=%s",
                    result.name,
                    attempt,
                    result.success,
                    result.duration_ms,
                    result.error_code,
                )

            if result.success or not self._should_retry(result) or attempt >= attempts:
                break

            self._log_tool_retry(result, attempt + 1)
            sleep(self._retry_backoff_seconds(attempt))

        if result is None:
            result = ToolResult(
                name=name,
                success=False,
                error="Tool call did not produce a result.",
                duration_ms=self._elapsed_ms(started_at),
                error_code=TOOL_EXECUTION_ERROR,
                error_message="Tool call did not produce a result.",
                retryable=False,
            )
        self._log_tool_finished(result)
        return result

    def _validate_tool(self, tool: BaseTool) -> None:
        if not isinstance(getattr(tool, "name", None), str) or not tool.name.strip():
            raise ValueError("Tool name must be a non-empty string.")
        if not isinstance(getattr(tool, "description", None), str):
            raise ValueError(f"Tool description must be a string: {tool.name}")
        if not isinstance(getattr(tool, "args_schema", None), dict):
            raise ValueError(f"Tool args_schema must be a dict: {tool.name}")

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
        if self._looks_like_rate_limit(normalized_message):
            return RATE_LIMIT, True
        if self._looks_like_mcp_server_unavailable(name, normalized_message):
            return MCP_SERVER_UNAVAILABLE, True
        http_status_code = self._http_status_code_from_error(normalized_message, exc=exc)
        if http_status_code is not None or self._looks_like_http_error(normalized_message, exc=exc):
            return HTTP_ERROR, self._is_retryable_http_status(http_status_code)
        if self._looks_like_parse_error(normalized_message):
            return PARSE_ERROR, False
        if self._looks_like_empty_result(normalized_message):
            return EMPTY_RESULT, False
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

    def _looks_like_rate_limit(self, message: str) -> bool:
        return any(marker in message for marker in ("429", "rate limit", "ratelimit", "too many requests"))

    def _http_status_code_from_error(self, message: str, exc: Exception | None = None) -> int | None:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        if isinstance(status_code, int):
            return status_code

        if "http 5xx" in message:
            return 500
        if "http 4xx" in message:
            return 400

        patterns = (
            r"\bhttp\s*(?P<status>[45]\d{2})\b",
            r"\bstatus(?:\s+code|_code)?\D+(?P<status>[45]\d{2})\b",
        )
        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                return int(match.group("status"))
        return None

    def _looks_like_http_error(self, message: str, exc: Exception | None = None) -> bool:
        exc_name = exc.__class__.__name__.lower() if exc is not None else ""
        return (
            "httpstatuserror" in exc_name
            or "httpstatuserror" in message
            or "http 4xx" in message
            or "http 5xx" in message
            or "status code" in message
            or "status_code" in message
        )

    def _is_retryable_http_status(self, status_code: int | None) -> bool:
        return status_code is not None and 500 <= status_code <= 599

    def _should_retry(self, result: ToolResult) -> bool:
        return bool(result.retryable and result.error_code in RETRYABLE_ERROR_CODES)

    def _retry_backoff_seconds(self, failed_attempt: int) -> float:
        return DEFAULT_RETRY_BACKOFF_SECONDS * (2 ** (failed_attempt - 1))

    def _normalize_max_retries(self, max_retries: int) -> int:
        try:
            return max(int(max_retries), 0)
        except (TypeError, ValueError):
            logger.warning("Invalid max_retries for tool call; using default: max_retries=%s", max_retries)
            return 1

    def _looks_like_parse_error(self, message: str) -> bool:
        return any(marker in message for marker in ("invalid json", "parse", "解析失败"))

    def _looks_like_empty_result(self, message: str) -> bool:
        return any(marker in message for marker in ("empty result", "no results", "结果为空"))

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

    def _log_tool_retry(self, result: ToolResult, attempt: int) -> None:
        logger.warning(
            "Tool call retrying: tool_name=%s attempt=%s error_code=%s",
            result.name,
            attempt,
            result.error_code,
        )
