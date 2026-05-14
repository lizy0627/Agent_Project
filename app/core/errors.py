from dataclasses import dataclass
from enum import StrEnum


class ErrorCode(StrEnum):
    API_KEY_MISSING = "api_key_missing"
    API_KEY_INVALID = "api_key_invalid"
    NETWORK_ERROR = "network_error"
    MODEL_TIMEOUT = "model_timeout"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class AgentError(Exception):
    """Base exception for application-level agent errors."""

    message: str
    code: ErrorCode = ErrorCode.UNKNOWN_ERROR
    status_code: int = 500

    def __str__(self) -> str:
        return self.message


class ApiKeyMissingError(AgentError):
    def __init__(self) -> None:
        super().__init__(
            message="DASHSCOPE_API_KEY is not configured.",
            code=ErrorCode.API_KEY_MISSING,
            status_code=400,
        )


class ApiKeyInvalidError(AgentError):
    def __init__(self) -> None:
        super().__init__(
            message="DashScope API Key is invalid or has no permission.",
            code=ErrorCode.API_KEY_INVALID,
            status_code=401,
        )


class ModelNetworkError(AgentError):
    def __init__(self) -> None:
        super().__init__(
            message="Unable to connect to DashScope. Please check the network.",
            code=ErrorCode.NETWORK_ERROR,
            status_code=503,
        )


class ModelTimeoutError(AgentError):
    def __init__(self) -> None:
        super().__init__(
            message="DashScope model request timed out. Please try again later.",
            code=ErrorCode.MODEL_TIMEOUT,
            status_code=504,
        )


class UnknownAgentError(AgentError):
    def __init__(self) -> None:
        super().__init__(
            message="Unexpected model service error. Please try again later.",
            code=ErrorCode.UNKNOWN_ERROR,
            status_code=500,
        )
