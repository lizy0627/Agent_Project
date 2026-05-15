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
        self.tool_manager = tool_manager or create_default_tool_manager(
            tavily_api_key=settings.tavily_api_key,
            web_search_provider=settings.web_search_provider,
        )

    def chat(self, messages: list[ChatMessage], model: str | None = None) -> AgentReply:
        """Send a chat request with complete context and return model text."""

        planned_call = self._plan_tool_call(messages)
        if planned_call and planned_call.name == "web_search":
            return self._handle_search_workflow(messages, planned_call, model=model)

        tool_result = self._call_planned_tool(planned_call)
        model_messages = self._messages_with_tool_result(messages, tool_result)
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

        stream, _tool_result = self.stream_chat_with_tool_result(messages, model=model)
        yield from stream

    def stream_chat_with_tool_result(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
    ) -> tuple[Iterator[str], ToolResult | None]:
        """Return a streaming iterator and the tool metadata used to build it."""

        planned_call = self._plan_tool_call(messages)
        if planned_call and planned_call.name == "web_search":
            reply = self._handle_search_workflow(messages, planned_call, model=model)
            return iter([reply.content]), reply.tool_result

        tool_result = self._call_planned_tool(planned_call)
        model_messages = self._messages_with_tool_result(messages, tool_result)
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
        return self._call_planned_tool(planned_call)

    def _call_planned_tool(self, planned_call: PlannedToolCall | None) -> ToolResult | None:
        if planned_call is None:
            logger.info("No tool call needed for current user message")
            return None

        logger.info("Tool call planned: name=%s", planned_call.name)
        return self.tool_manager.call(planned_call.name, **planned_call.arguments)

    def _handle_search_workflow(
        self,
        messages: list[ChatMessage],
        planned_call: PlannedToolCall,
        model: str | None = None,
    ) -> AgentReply:
        """Run search, read top pages, and ask the model to synthesize an answer."""

        search_result = self._call_search_workflow_tool("web_search", **planned_call.arguments)
        workflow_step_results = [search_result]
        search_payload = search_result.result if isinstance(search_result.result, dict) else {}
        search_items = search_payload.get("results", []) if search_result.success else []

        pages: list[dict[str, Any]] = []
        if isinstance(search_items, list):
            for item in search_items[:3]:
                if not isinstance(item, dict):
                    continue

                url = str(item.get("url") or "").strip()
                if not url:
                    continue

                reader_result = self._call_search_workflow_tool("web_reader", url=url)
                workflow_step_results.append(reader_result)
                page_content = ""
                final_url = url
                if reader_result.success and isinstance(reader_result.result, dict):
                    page_content = str(reader_result.result.get("content") or "")
                    final_url = str(reader_result.result.get("url") or url)

                pages.append(
                    {
                        "title": item.get("title", ""),
                        "url": final_url,
                        "search_snippet": item.get("content") or item.get("snippet") or "",
                        "score": item.get("score"),
                        "read_success": reader_result.success,
                        "read_error": reader_result.error,
                        "content": page_content,
                    }
                )

        workflow_payload = {
            "query": planned_call.arguments.get("query", self._latest_user_message(messages)),
            "search_success": search_result.success,
            "search_error": search_result.error,
            "search_results": search_items,
            "read_pages": pages,
        }
        workflow_duration_ms = self._sum_tool_durations(workflow_step_results)
        workflow_result = ToolResult(
            name="web_search",
            success=search_result.success,
            result=workflow_payload,
            error=search_result.error,
            duration_ms=workflow_duration_ms,
        )
        model_messages = self._messages_with_search_workflow_result(messages, workflow_result)
        reply = self._complete_chat(model_messages, model=model)
        return AgentReply(content=reply, tool_result=workflow_result)

    def _call_search_workflow_tool(self, name: str, **kwargs: Any) -> ToolResult:
        result = self.tool_manager.call(name, **kwargs)
        logger.info(
            "Search workflow step finished: name=%s success=%s duration_ms=%s",
            result.name,
            result.success,
            result.duration_ms,
        )
        return result

    def _sum_tool_durations(self, results: list[ToolResult]) -> float:
        return round(sum(result.duration_ms or 0 for result in results), 2)

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

        if self._looks_like_search_request(user_message):
            return PlannedToolCall(
                name="web_search",
                arguments={"query": user_message, "max_results": 5},
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
        if tool_result.name == "web_search":
            search_system_prompt = (
                "你正在基于联网搜索结果回答用户问题。必须遵守："
                "1. 只基于搜索结果回答，不编造搜索结果中没有的信息；"
                "2. 对多个来源进行交叉总结，合并重复信息，指出关键信息差异；"
                "3. 如果搜索结果不足、冲突或无法支持结论，要明确说明信息不足；"
                "4. 使用中文分点回答，结构清晰；"
                "5. 最后列出“参考来源”，来源格式必须是 [标题](URL)。"
            )
            tool_context = (
                "已先执行 web_search 联网搜索工具。请根据下面的 JSON 搜索结果回答用户最初的问题。\n"
                f"{json.dumps(payload, ensure_ascii=False)}"
            )
            return [
                *messages,
                {
                    "role": "system",
                    "content": search_system_prompt,
                },
                {
                    "role": "user",
                    "content": tool_context,
                },
            ]

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

    def _messages_with_search_workflow_result(
        self,
        messages: list[ChatMessage],
        tool_result: ToolResult,
    ) -> list[ChatMessage]:
        payload = {
            "tool_name": tool_result.name,
            "success": tool_result.success,
            "result": tool_result.result,
            "error": tool_result.error,
        }
        search_system_prompt = (
            "你是一个严谨的联网研究助手。你已经获得 Tavily 搜索摘要和前 3 个网页的正文摘录。"
            "请只基于这些材料回答用户最初的问题，不要编造材料中没有的信息。"
            "需要对多个来源进行交叉总结，合并重复信息，并说明材料中的差异或不确定性。"
            "如果搜索或网页读取信息不足，要明确说明哪些结论无法确认。"
            "最终回答必须使用中文，并包含以下四个部分："
            "一、结论；二、关键要点；三、详细解释；四、参考来源。"
            "参考来源必须使用 Markdown 链接格式：[标题](URL)。"
        )
        tool_context = (
            "已完成多步骤联网搜索工作流：用户问题 -> Tavily 搜索 -> 读取前 3 个网页 -> 汇总材料。"
            "请基于下面 JSON 中的搜索摘要和网页正文生成最终回答。\n"
            f"{json.dumps(payload, ensure_ascii=False)}"
        )
        return [
            *messages,
            {
                "role": "system",
                "content": search_system_prompt,
            },
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

    def _looks_like_search_request(self, message: str) -> bool:
        """Return True when a user asks for current or external web information."""

        clean_message = message.strip()
        if not clean_message:
            return False

        lowered = message.lower()
        casual_phrases = (
            "你好",
            "您好",
            "在吗",
            "谢谢",
            "你是谁",
            "你好吗",
            "你现在好吗",
            "你怎么样",
            "hello",
            "hi",
            "thanks",
            "thank you",
            "who are you",
            "how are you",
        )
        if lowered in casual_phrases:
            return False

        strong_keywords = (
            "联网搜索",
            "网络搜索",
            "网上搜索",
            "搜索",
            "查一下",
            "帮我查",
            "联网",
            "最新",
            "新闻",
            "资料",
            "官网",
            "最近",
            "价格",
            "github",
            "项目",
            "论文",
            "教程",
            "search",
            "latest",
            "news",
            "current",
            "today",
            "recent",
            "website",
            "official",
            "price",
        )
        if any(keyword in lowered for keyword in strong_keywords):
            return True

        ambiguous_keywords = (
            "今天",
            "现在",
            "是什么",
            "怎么样",
        )
        if not any(keyword in lowered for keyword in ambiguous_keywords):
            return False

        if lowered.startswith("你"):
            return False

        if lowered.startswith("我") and not self._has_external_subject_hint(lowered):
            return False

        return self._has_external_subject_hint(lowered)

    def _has_external_subject_hint(self, lowered_message: str) -> bool:
        external_subject_keywords = (
            "公司",
            "产品",
            "品牌",
            "平台",
            "官网",
            "网站",
            "app",
            "软件",
            "版本",
            "发布",
            "更新",
            "技术",
            "框架",
            "库",
            "api",
            "模型",
            "价格",
            "股价",
            "github",
            "项目",
            "论文",
            "教程",
            "文档",
            "资料",
            "新闻",
            "天气",
            "汇率",
            "股票",
            "基金",
            "国家",
            "城市",
            "地区",
            "总统",
            "政策",
            "赛事",
            "榜单",
            "招聘",
            "fastapi",
            "python",
            "javascript",
            "typescript",
            "react",
            "vue",
            "openai",
            "dashscope",
            "tavily",
        )
        if any(keyword in lowered_message for keyword in external_subject_keywords):
            return True

        return bool(re.search(r"[a-z0-9][a-z0-9_.-]{1,}", lowered_message))
