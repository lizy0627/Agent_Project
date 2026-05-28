from typing import Iterator

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    OpenAIError,
)

from app.core.config import Settings
from app.core.errors import (
    ApiKeyInvalidError,
    ApiKeyMissingError,
    ModelNetworkError,
    ModelTimeoutError,
    UnknownAgentError,
)
from app.core.logger import get_logger
from app.services.agent_types import ChatMessage


logger = get_logger(__name__)


class LLMClient:
    """DashScope OpenAI-compatible client for blocking and streaming calls only."""

    def __init__(self, settings: Settings) -> None:
        if not settings.dashscope_api_key:
            raise ApiKeyMissingError()

        self.model = settings.dashscope_model
        self.client = OpenAI(
            api_key=settings.dashscope_api_key,
            base_url=settings.dashscope_base_url,
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
            except AuthenticationError as exc:
                logger.warning("DashScope authentication failed: %s", exc.__class__.__name__)
                raise ApiKeyInvalidError() from exc
            except APITimeoutError as exc:
                logger.warning("DashScope request timed out: %s", exc.__class__.__name__)
                raise ModelTimeoutError() from exc
            except APIConnectionError as exc:
                logger.warning("DashScope network error: %s", exc.__class__.__name__)
                raise ModelNetworkError() from exc
            except APIStatusError as exc:
                logger.warning(
                    "DashScope API status error: class=%s status=%s",
                    exc.__class__.__name__,
                    exc.status_code,
                )
                if exc.status_code in {401, 403}:
                    raise ApiKeyInvalidError() from exc
                if exc.status_code in {408, 504}:
                    raise ModelTimeoutError() from exc
                raise UnknownAgentError() from exc
            except OpenAIError as exc:
                logger.warning("DashScope SDK error: %s", exc.__class__.__name__)
                raise UnknownAgentError() from exc
            except Exception as exc:
                logger.exception("Unexpected error while calling DashScope")
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
            except AuthenticationError as exc:
                logger.warning("DashScope authentication failed: %s", exc.__class__.__name__)
                raise ApiKeyInvalidError() from exc
            except APITimeoutError as exc:
                logger.warning("DashScope streaming request timed out: %s", exc.__class__.__name__)
                raise ModelTimeoutError() from exc
            except APIConnectionError as exc:
                logger.warning("DashScope streaming network error: %s", exc.__class__.__name__)
                raise ModelNetworkError() from exc
            except APIStatusError as exc:
                logger.warning(
                    "DashScope streaming API status error: class=%s status=%s",
                    exc.__class__.__name__,
                    exc.status_code,
                )
                if exc.status_code in {401, 403}:
                    raise ApiKeyInvalidError() from exc
                if exc.status_code in {408, 504}:
                    raise ModelTimeoutError() from exc
                raise UnknownAgentError() from exc
            except OpenAIError as exc:
                logger.warning("DashScope streaming SDK error: %s", exc.__class__.__name__)
                raise UnknownAgentError() from exc
            except Exception as exc:
                logger.exception("Unexpected error while streaming from DashScope")
                raise UnknownAgentError() from exc
