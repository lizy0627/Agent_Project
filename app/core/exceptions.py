from dataclasses import dataclass
from enum import StrEnum

from fastapi.responses import JSONResponse


class ErrorCode(StrEnum):
    API_KEY_MISSING = "API_KEY_MISSING"
    API_KEY_INVALID = "API_KEY_INVALID"
    AUTH_ERROR = "AUTH_ERROR"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    DOCUMENT_NOT_FOUND = "DOCUMENT_NOT_FOUND"
    INVALID_ARGUMENTS = "INVALID_ARGUMENTS"
    MCP_SERVER_UNAVAILABLE = "MCP_SERVER_UNAVAILABLE"
    MEMORY_ERROR = "MEMORY_ERROR"
    MODEL_PROVIDER_ERROR = "MODEL_PROVIDER_ERROR"
    MODEL_TIMEOUT = "MODEL_TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    NOT_FOUND = "NOT_FOUND"
    RATE_LIMIT = "RATE_LIMIT"
    TOOL_EXECUTION_ERROR = "TOOL_EXECUTION_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


@dataclass
class AgentError(Exception):
    """Base exception for application-level errors safe to expose as API codes."""

    message: str
    code: str | ErrorCode = ErrorCode.UNKNOWN_ERROR
    status_code: int = 500
    retryable: bool = False

    def __str__(self) -> str:
        return self.message


class ToolExecutionError(AgentError):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message=message or "Tool call failed. Please try again or adjust your request.",
            code=ErrorCode.TOOL_EXECUTION_ERROR,
            status_code=500,
            retryable=False,
        )


class ModelProviderError(AgentError):
    def __init__(
        self,
        message: str | None = None,
        code: str | ErrorCode = ErrorCode.MODEL_PROVIDER_ERROR,
        status_code: int = 502,
        retryable: bool = True,
    ) -> None:
        super().__init__(
            message=message or "Model provider request failed. Please try again later.",
            code=code,
            status_code=status_code,
            retryable=retryable,
        )


class MemoryError(AgentError):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message=message or "Memory service failed. Please try again later.",
            code=ErrorCode.MEMORY_ERROR,
            status_code=500,
            retryable=True,
        )


class ApiKeyMissingError(ModelProviderError):
    def __init__(self) -> None:
        super().__init__(
            message="API_KEY is not configured. Add API_KEY to .env.",
            code=ErrorCode.API_KEY_MISSING,
            status_code=400,
            retryable=False,
        )


class ApiKeyInvalidError(ModelProviderError):
    def __init__(self) -> None:
        super().__init__(
            message="DashScope API Key is invalid or has no permission.",
            code=ErrorCode.API_KEY_INVALID,
            status_code=401,
            retryable=False,
        )


class AuthenticationRequiredError(AgentError):
    def __init__(self) -> None:
        super().__init__(
            message="Authentication required.",
            code=ErrorCode.AUTH_REQUIRED,
            status_code=401,
            retryable=False,
        )


class ModelNetworkError(ModelProviderError):
    def __init__(self) -> None:
        super().__init__(
            message="Unable to connect to DashScope. Please check the network.",
            code=ErrorCode.NETWORK_ERROR,
            status_code=503,
            retryable=True,
        )


class ModelTimeoutError(ModelProviderError):
    def __init__(self) -> None:
        super().__init__(
            message="DashScope model request timed out. Please try again later.",
            code=ErrorCode.MODEL_TIMEOUT,
            status_code=504,
            retryable=True,
        )


class UnknownAgentError(AgentError):
    def __init__(self) -> None:
        super().__init__(
            message="Unexpected model service error. Please try again later.",
            code=ErrorCode.UNKNOWN_ERROR,
            status_code=500,
            retryable=True,
        )


class MCPServerUnavailableError(AgentError):
    def __init__(self) -> None:
        super().__init__(
            message="MCP service is unavailable. Please check whether the MCP server is running.",
            code=ErrorCode.MCP_SERVER_UNAVAILABLE,
            status_code=503,
            retryable=True,
        )


class InvalidArgumentsError(AgentError):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message=message or "Invalid request parameters. Please check the request body.",
            code=ErrorCode.INVALID_ARGUMENTS,
            status_code=422,
            retryable=False,
        )


class NotFoundError(AgentError):
    def __init__(self, message: str | None = None, code: str | ErrorCode = ErrorCode.NOT_FOUND) -> None:
        super().__init__(
            message=message or "Requested resource was not found.",
            code=code,
            status_code=404,
            retryable=False,
        )


def error_payload(
    error: AgentError,
    *,
    message: str | None = None,
    code: str | ErrorCode | None = None,
    request_id: str | None = None,
    detail: dict | None = None,
) -> dict:
    """Return the public API error payload without traceback or internal details."""

    error_body = {
        "code": str(code or error.code),
        "message": message or public_error_message(error),
        "retryable": error.retryable,
    }
    if request_id is not None:
        error_body["request_id"] = request_id
    if detail is not None:
        error_body["detail"] = detail

    return {
        "success": False,
        "error": error_body,
    }


def error_response(
    error: AgentError,
    *,
    headers: dict[str, str] | None = None,
    message: str | None = None,
    code: str | ErrorCode | None = None,
    request_id: str | None = None,
    detail: dict | None = None,
    status_code: int | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code or error.status_code,
        content=error_payload(error, message=message, code=code, request_id=request_id, detail=detail),
        headers=headers,
    )


def public_error_message(error: AgentError) -> str:
    messages = {
        ErrorCode.API_KEY_MISSING: "API_KEY is not configured. Add API_KEY to .env.",
        ErrorCode.API_KEY_INVALID: "DashScope API Key 无效或没有权限，请检查配置。",
        ErrorCode.AUTH_ERROR: "Authentication failed.",
        ErrorCode.AUTH_REQUIRED: "Authentication required.",
        ErrorCode.DOCUMENT_NOT_FOUND: "文档不存在或已被删除。",
        ErrorCode.INVALID_ARGUMENTS: "请求参数非法，请检查请求内容。",
        ErrorCode.MCP_SERVER_UNAVAILABLE: "MCP 服务不可用，请确认 MCP Server 已启动并可访问。",
        ErrorCode.MEMORY_ERROR: "记忆服务暂时异常，请稍后重试。",
        ErrorCode.MODEL_PROVIDER_ERROR: "模型服务暂时异常，请稍后重试。",
        ErrorCode.MODEL_TIMEOUT: "模型请求超时，请稍后重试。",
        ErrorCode.NETWORK_ERROR: "网络连接失败，请检查网络或稍后重试。",
        ErrorCode.NOT_FOUND: "请求的资源不存在。",
        ErrorCode.TOOL_EXECUTION_ERROR: "工具调用失败，请调整问题后重试。",
        ErrorCode.UNKNOWN_ERROR: "服务暂时异常，请稍后重试。",
        ErrorCode.RATE_LIMIT: "请求过于频繁，请稍后重试。",
    }
    try:
        code = ErrorCode(str(error.code))
    except ValueError:
        return messages[ErrorCode.UNKNOWN_ERROR]
    return messages.get(code, messages[ErrorCode.UNKNOWN_ERROR])
