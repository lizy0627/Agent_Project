from dataclasses import dataclass
from enum import StrEnum


class ErrorCode(StrEnum):
    API_KEY_MISSING = "API_KEY_MISSING"
    API_KEY_INVALID = "API_KEY_INVALID"
    NETWORK_ERROR = "NETWORK_ERROR"
    MODEL_TIMEOUT = "MODEL_TIMEOUT"
    TOOL_EXECUTION_ERROR = "TOOL_EXECUTION_ERROR"
    MCP_SERVER_UNAVAILABLE = "MCP_SERVER_UNAVAILABLE"
    INVALID_ARGUMENTS = "INVALID_ARGUMENTS"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


@dataclass
class AgentError(Exception):
    """Base exception for application-level agent errors."""

    message: str
    code: ErrorCode = ErrorCode.UNKNOWN_ERROR
    status_code: int = 500
    retryable: bool = False

    def __str__(self) -> str:
        return self.message


class ApiKeyMissingError(AgentError):
    def __init__(self) -> None:
        super().__init__(
            message="DASHSCOPE_API_KEY is not configured.",
            code=ErrorCode.API_KEY_MISSING,
            status_code=400,
            retryable=False,
        )


class ApiKeyInvalidError(AgentError):
    def __init__(self) -> None:
        super().__init__(
            message="DashScope API Key is invalid or has no permission.",
            code=ErrorCode.API_KEY_INVALID,
            status_code=401,
            retryable=False,
        )


class ModelNetworkError(AgentError):
    def __init__(self) -> None:
        super().__init__(
            message="Unable to connect to DashScope. Please check the network.",
            code=ErrorCode.NETWORK_ERROR,
            status_code=503,
            retryable=True,
        )


class ModelTimeoutError(AgentError):
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


class ToolExecutionError(AgentError):
    def __init__(self) -> None:
        super().__init__(
            message="Tool call failed. Please try again or adjust your request.",
            code=ErrorCode.TOOL_EXECUTION_ERROR,
            status_code=500,
            retryable=False,
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
    def __init__(self) -> None:
        super().__init__(
            message="Invalid request parameters. Please check the request body.",
            code=ErrorCode.INVALID_ARGUMENTS,
            status_code=422,
            retryable=False,
        )
