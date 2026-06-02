from typing import Any, Iterator

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    OpenAIError,
)

from backend.app.core.config import Settings
from backend.app.core.exceptions import (
    AgentError,
    ApiKeyInvalidError,
    ApiKeyMissingError,
    ErrorCode,
    InvalidArgumentsError,
    ModelNetworkError,
    ModelProviderError,
    ModelTimeoutError,
    UnknownAgentError,
)
from backend.app.core.logger import get_logger
from backend.app.services.agent_types import ChatMessage


logger = get_logger(__name__)
RATE_LIMIT_MESSAGE = "Model provider rate limit exceeded. Please try again later."


class LLMClient:
    """DashScope OpenAI-compatible client for blocking and streaming calls only."""

    def __init__(self, settings: Settings) -> None:
        if not settings.api_key:
            raise ApiKeyMissingError()

        self.model = settings.model_name
        self.client = OpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=settings.dashscope_timeout_seconds,
        )

    def complete_chat(self, messages: list[ChatMessage], model: str | None = None) -> str:
        """Call the chat completion API and return model text."""

        target_model = model or self.model

        try:
            completion = self.client.chat.completions.create(
                model=target_model,
                messages=messages,
            )
        except OpenAIError as exc:
            _log_openai_error("chat", exc)
            raise _map_openai_error(exc) from exc
        except Exception as exc:
            logger.warning("Unexpected error while calling DashScope: class=%s", exc.__class__.__name__)
            raise UnknownAgentError() from exc

        reply = completion.choices[0].message.content
        return reply or ""

    def stream_complete_chat(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
    ) -> Iterator[str]:
        """Call the streaming chat completion API and yield model text chunks."""

        target_model = model or self.model

        try:
            stream = self.client.chat.completions.create(
                model=target_model,
                messages=messages,
                stream=True,
            )
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                content = delta.content if delta else None
                if content:
                    yield content
        except OpenAIError as exc:
            _log_openai_error("streaming chat", exc)
            raise _map_openai_error(exc) from exc
        except Exception as exc:
            logger.warning("Unexpected error while streaming from DashScope: class=%s", exc.__class__.__name__)
            raise UnknownAgentError() from exc


def _map_openai_error(exc: OpenAIError) -> AgentError:
    if isinstance(exc, AuthenticationError):
        return ApiKeyInvalidError()
    if isinstance(exc, APITimeoutError):
        return ModelTimeoutError()
    if isinstance(exc, APIConnectionError):
        return ModelNetworkError()
    if isinstance(exc, APIStatusError):
        return _map_api_status_error(exc)

    return ModelProviderError()


def _map_api_status_error(exc: APIStatusError) -> AgentError:
    status_code = exc.status_code

    if status_code in {401, 403}:
        return ApiKeyInvalidError()
    if status_code in {408, 504}:
        return ModelTimeoutError()
    if status_code == 429:
        return ModelProviderError(
            message=RATE_LIMIT_MESSAGE,
            code=ErrorCode.RATE_LIMIT,
            status_code=429,
            retryable=True,
        )
    if status_code in {400, 422}:
        return InvalidArgumentsError()
    if 500 <= status_code <= 599:
        return ModelProviderError(status_code=status_code, retryable=True)

    return ModelProviderError(status_code=status_code, retryable=False)


def _log_openai_error(operation: str, exc: OpenAIError) -> None:
    logger.warning(
        "DashScope %s error: class=%s status=%s error_type=%s",
        operation,
        exc.__class__.__name__,
        getattr(exc, "status_code", None),
        _openai_error_type(exc),
    )


def _openai_error_type(exc: OpenAIError) -> str | None:
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        return _error_type_from_body(body)
    return None


def _error_type_from_body(body: dict[str, Any]) -> str | None:
    error = body.get("error")
    if isinstance(error, dict):
        value = error.get("type") or error.get("code")
        return str(value) if value else None

    value = body.get("type") or body.get("code")
    return str(value) if value else None
