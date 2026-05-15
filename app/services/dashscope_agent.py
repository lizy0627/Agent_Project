from dataclasses import dataclass
import json
import re
from typing import Any, Iterator

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
from app.tools import create_default_tool_manager
from app.tools.base import ToolResult
from app.tools.tool_manager import ToolManager


logger = get_logger(__name__)
ChatMessage = dict[str, str]


@dataclass(frozen=True)
class PlannedToolCall:
    """A local tool call selected for the latest user message."""

    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class AgentReply:
    """Final agent reply plus optional tool execution metadata."""

    content: str
    tool_result: ToolResult | None = None

    @property
    def used_tool(self) -> bool:
        return self.tool_result is not None


class DashScopeAgent:
    """Minimal agent that calls DashScope through the OpenAI-compatible API."""

    def __init__(self, settings: Settings, tool_manager: ToolManager | None = None) -> None:
        if not settings.dashscope_api_key:
            raise ApiKeyMissingError()

        self.client = OpenAI(
            api_key=settings.dashscope_api_key,
            base_url=settings.dashscope_base_url,
            timeout=settings.dashscope_timeout_seconds,
        )
        self.model = settings.dashscope_model
        self.tool_manager = tool_manager or create_default_tool_manager()

    def chat(self, messages: list[ChatMessage], model: str | None = None) -> AgentReply:
        """Send a chat request with complete context and return model text."""

        model_messages, tool_result = self.prepare_chat_messages(messages)
        reply = self._complete_chat(model_messages, model=model)
        return AgentReply(content=reply, tool_result=tool_result)

    def _complete_chat(self, messages: list[ChatMessage], model: str | None = None) -> str:
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

    def stream_chat(self, messages: list[ChatMessage], model: str | None = None) -> Iterator[str]:
        """Stream a chat request with complete context."""

        model_messages, _tool_result = self.prepare_chat_messages(messages)
        yield from self._stream_complete_chat(model_messages, model=model)

    def stream_chat_with_tool_result(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
    ) -> tuple[Iterator[str], ToolResult | None]:
        """Return a streaming iterator and the tool metadata used to build it."""

        model_messages, tool_result = self.prepare_chat_messages(messages)
        return self._stream_complete_chat(model_messages, model=model), tool_result

    def prepare_chat_messages(
        self,
        messages: list[ChatMessage],
    ) -> tuple[list[ChatMessage], ToolResult | None]:
        """Apply optional local tool context before calling the model."""

        tool_result = self._maybe_call_tool(messages)
        return self._messages_with_tool_result(messages, tool_result), tool_result

    def _stream_complete_chat(
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

    def _maybe_call_tool(self, messages: list[ChatMessage]) -> ToolResult | None:
        planned_call = self._plan_tool_call(messages)
        if planned_call is None:
            logger.info("No tool call needed for current user message")
            return None

        logger.info("Tool call planned: name=%s", planned_call.name)
        return self.tool_manager.call(planned_call.name, **planned_call.arguments)

    def _plan_tool_call(self, messages: list[ChatMessage]) -> PlannedToolCall | None:
        user_message = self._latest_user_message(messages)
        if not user_message:
            return None

        if self._looks_like_time_request(user_message):
            return PlannedToolCall(
                name="get_current_time",
                arguments={"timezone": "Asia/Shanghai"},
            )

        expression = self._extract_calculation_expression(user_message)
        if expression:
            return PlannedToolCall(
                name="calculate",
                arguments={"expression": expression},
            )

        text_to_summarize = self._extract_text_to_summarize(user_message)
        if text_to_summarize:
            return PlannedToolCall(
                name="summarize_text",
                arguments={"text": text_to_summarize},
            )

        return None

    def _messages_with_tool_result(
        self,
        messages: list[ChatMessage],
        tool_result: ToolResult | None,
    ) -> list[ChatMessage]:
        if tool_result is None:
            return messages

        payload = {
            "tool_name": tool_result.name,
            "success": tool_result.success,
            "result": tool_result.result,
            "error": tool_result.error,
        }
        tool_context = (
            "已先执行本地工具调用。请基于工具结果回答用户最初的问题；"
            "如果工具失败，请说明失败原因并给出可行的下一步。\n"
            f"{json.dumps(payload, ensure_ascii=False)}"
        )
        return [
            *messages,
            {
                "role": "user",
                "content": tool_context,
            },
        ]

    def _latest_user_message(self, messages: list[ChatMessage]) -> str:
        for message in reversed(messages):
            if message.get("role") == "user":
                return message.get("content", "")
        return ""

    def _looks_like_time_request(self, message: str) -> bool:
        lowered = message.lower()
        time_keywords = (
            "现在几点",
            "当前时间",
            "现在时间",
            "今天几号",
            "今天日期",
            "当前日期",
            "current time",
            "what time",
            "today's date",
            "today date",
        )
        return any(keyword in lowered for keyword in time_keywords)

    def _extract_calculation_expression(self, message: str) -> str | None:
        lowered = message.lower()
        has_calculation_intent = any(
            keyword in lowered
            for keyword in ("计算", "算一下", "等于多少", "calculate", "calc", "=", "求值")
        )
        if not has_calculation_intent:
            return None

        normalized = (
            message.replace("×", "*")
            .replace("÷", "/")
            .replace("^", "**")
            .replace("（", "(")
            .replace("）", ")")
        )
        allowed_chunks = re.findall(
            r"(?:sqrt|sin|cos|tan|log10|log|ceil|floor|round|abs|pow|pi|tau|e|[0-9+\-*/().,%\s])+",
            normalized,
            flags=re.IGNORECASE,
        )
        candidates = [
            chunk.strip().rstrip("=?？。")
            for chunk in allowed_chunks
            if any(char.isdigit() for char in chunk)
        ]
        if not candidates:
            return None

        expression = max(candidates, key=len).replace(",", "")
        if len(re.findall(r"[+\-*/%()]|\*\*", expression)) == 0:
            return None
        return expression

    def _extract_text_to_summarize(self, message: str) -> str | None:
        lowered = message.lower()
        if not any(keyword in lowered for keyword in ("总结", "摘要", "概括", "summarize", "summary")):
            return None

        split_match = re.search(r"[:：]\s*(.+)", message, flags=re.DOTALL)
        if split_match:
            text = split_match.group(1).strip()
        else:
            text = re.sub(
                r"^(请|帮我|麻烦)?(总结|摘要|概括|summarize|summary)(一下|下)?",
                "",
                message,
                flags=re.IGNORECASE,
            ).strip()

        return text if len(text) >= 20 else None
