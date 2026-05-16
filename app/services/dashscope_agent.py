import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
import re
from time import perf_counter
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
DEFAULT_WEB_SEARCH_MAX_RESULTS = 3
DEFAULT_SEARCH_WORKFLOW_READ_TOP_K = 3
MAX_SEARCH_WORKFLOW_READ_TOP_K = 3
WEB_SEARCH_TOOL_ARGUMENTS = {"query", "max_results", "search_depth"}
MAX_SEARCH_SUMMARY_RESULTS = 3
MAX_PAGE_CONTENT_CHARS = 3000
MAX_SEARCH_CONTEXT_CHARS = 9000


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

        workflow_started_at = perf_counter()
        query = str(planned_call.arguments.get("query", self._latest_user_message(messages)))
        search_kwargs = self._web_search_tool_arguments(planned_call.arguments, query=query)
        read_top_k = min(
            self._positive_int(
                planned_call.arguments.get("read_top_k"),
                default=DEFAULT_SEARCH_WORKFLOW_READ_TOP_K,
            ),
            MAX_SEARCH_WORKFLOW_READ_TOP_K,
        )
        logger.info("Search workflow started: query=%s", query[:200])
        search_result = self._call_search_workflow_tool("web_search", **search_kwargs)
        workflow_step_results = [search_result]
        search_payload = search_result.result if isinstance(search_result.result, dict) else {}
        search_items = search_payload.get("results", []) if search_result.success else []
        search_result_count = len(search_items) if isinstance(search_items, list) else 0
        logger.info(
            "Search workflow web_search finished: success=%s result_count=%s error=%s",
            search_result.success,
            search_result_count,
            search_result.error,
        )

        pages: list[dict[str, Any]] = []
        if isinstance(search_items, list):
            selected_items = self._select_search_items_for_reading(search_items, read_top_k)
            logger.info(
                "Search workflow selected pages for reading: requested=%s selected=%s",
                read_top_k,
                len(selected_items),
            )
            reader_pairs = self._read_search_pages_concurrently(selected_items)
            for item, reader_result in reader_pairs:
                workflow_step_results.append(reader_result)
                if not reader_result.success:
                    logger.warning(
                        "Search workflow web_reader failed, skipped: url=%s error=%s",
                        str(item.get("url") or "").strip(),
                        reader_result.error,
                    )
                    continue

                url = str(item.get("url") or "").strip()
                logger.info(
                    "Search workflow web_reader finished: url=%s success=%s error=%s",
                    url,
                    reader_result.success,
                    reader_result.error,
                )
                page_content = ""
                final_url = url
                if isinstance(reader_result.result, dict):
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

        compact_search_items, compact_pages = self._compact_search_workflow_context(
            query=query,
            search_success=search_result.success,
            search_error=search_result.error,
            search_items=search_items if isinstance(search_items, list) else [],
            pages=pages,
            max_context_chars=MAX_SEARCH_CONTEXT_CHARS,
        )
        workflow_payload = {
            "query": query,
            "search_success": search_result.success,
            "search_error": search_result.error,
            "search_results": compact_search_items,
            "read_pages": compact_pages,
        }
        context_length = len(json.dumps(workflow_payload, ensure_ascii=False))
        logger.info(
            "Search workflow context compacted: search_results=%s/%s read_pages=%s/%s context_chars=%s",
            len(compact_search_items),
            search_result_count,
            len(compact_pages),
            len(pages),
            context_length,
        )
        workflow_duration_ms = self._sum_tool_durations(workflow_step_results)
        workflow_result = ToolResult(
            name="web_search",
            success=search_result.success,
            result=workflow_payload,
            error=search_result.error,
            duration_ms=workflow_duration_ms,
        )
        model_messages = self._messages_with_search_workflow_result(messages, workflow_result)
        logger.info(
            "Search workflow summary prepared: search_success=%s read_pages=%s successful_reads=%s",
            search_result.success,
            len(pages),
            sum(1 for page in pages if page.get("read_success")),
        )
        logger.info("[SearchWorkflow] llm summarize start")
        summarize_started_at = perf_counter()
        try:
            reply = self._complete_chat(model_messages, model=model)
        finally:
            logger.info(
                "[SearchWorkflow] llm summarize done, cost=%.2fs",
                self._elapsed_seconds(summarize_started_at),
            )
        logger.info(
            "[SearchWorkflow] workflow done, cost=%.2fs",
            self._elapsed_seconds(workflow_started_at),
        )
        return AgentReply(content=reply, tool_result=workflow_result)

    def _call_search_workflow_tool(self, name: str, **kwargs: Any) -> ToolResult:
        started_at = perf_counter()
        url = str(kwargs.get("url") or "").strip()
        if name == "web_reader":
            logger.info("[SearchWorkflow] web_reader start url=%s", url)
        else:
            logger.info("[SearchWorkflow] %s start", name)

        result = self.tool_manager.call(name, **kwargs)
        cost = self._elapsed_seconds(started_at)
        if name == "web_reader":
            logger.info("[SearchWorkflow] web_reader done url=%s, cost=%.2fs", url, cost)
        else:
            logger.info("[SearchWorkflow] %s done, cost=%.2fs", name, cost)
        logger.info(
            "Search workflow step finished: name=%s success=%s duration_ms=%s",
            result.name,
            result.success,
            result.duration_ms,
        )
        return result

    def _read_search_pages_concurrently(
        self,
        selected_items: list[dict[str, Any]],
    ) -> list[tuple[dict[str, Any], ToolResult]]:
        if not selected_items:
            return []

        started_at = perf_counter()
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            reader_pairs = asyncio.run(self._read_search_pages_concurrently_async(selected_items))
        else:
            with ThreadPoolExecutor(max_workers=1) as executor:
                reader_pairs = executor.submit(
                    lambda: asyncio.run(self._read_search_pages_concurrently_async(selected_items))
                ).result()

        logger.info(
            "[SearchWorkflow] web_reader batch done, count=%s, cost=%.2fs",
            len(selected_items),
            self._elapsed_seconds(started_at),
        )
        return reader_pairs

    async def _read_search_pages_concurrently_async(
        self,
        selected_items: list[dict[str, Any]],
    ) -> list[tuple[dict[str, Any], ToolResult]]:
        tasks = [
            asyncio.to_thread(
                self._call_search_workflow_tool,
                "web_reader",
                url=str(item.get("url") or "").strip(),
            )
            for item in selected_items
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        reader_pairs: list[tuple[dict[str, Any], ToolResult]] = []
        for item, result in zip(selected_items, results):
            url = str(item.get("url") or "").strip()
            if isinstance(result, Exception):
                logger.warning(
                    "Search workflow web_reader raised, skipped: url=%s error=%s",
                    url,
                    result,
                )
                continue
            reader_pairs.append((item, result))
        return reader_pairs

    def _sum_tool_durations(self, results: list[ToolResult]) -> float:
        return round(sum(result.duration_ms or 0 for result in results), 2)

    def _elapsed_seconds(self, started_at: float) -> float:
        return round(perf_counter() - started_at, 2)

    def _web_search_tool_arguments(self, arguments: dict[str, Any], query: str) -> dict[str, Any]:
        tool_arguments = {
            key: value for key, value in arguments.items() if key in WEB_SEARCH_TOOL_ARGUMENTS
        }
        tool_arguments["query"] = query
        tool_arguments.setdefault("max_results", DEFAULT_WEB_SEARCH_MAX_RESULTS)
        tool_arguments.setdefault("search_depth", "basic")
        return tool_arguments

    def _select_search_items_for_reading(
        self,
        search_items: list[Any],
        read_top_k: int,
    ) -> list[dict[str, Any]]:
        valid_items = [
            item
            for item in search_items
            if isinstance(item, dict) and self._is_valid_web_url(str(item.get("url") or "").strip())
        ]
        return sorted(valid_items, key=self._search_score, reverse=True)[:read_top_k]

    def _is_valid_web_url(self, url: str) -> bool:
        return url.startswith(("http://", "https://"))

    def _search_score(self, item: dict[str, Any]) -> float:
        try:
            return float(item.get("score") or 0)
        except (TypeError, ValueError):
            return 0

    def _positive_int(self, value: Any, default: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return max(parsed, 1)

    def _compact_search_workflow_context(
        self,
        query: str,
        search_success: bool,
        search_error: str | None,
        search_items: list[Any],
        pages: list[dict[str, Any]],
        max_context_chars: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        compact_search_items = self._compact_search_results(search_items)
        compact_pages = self._compact_pages(pages)

        while compact_pages and self._workflow_context_length(
            query,
            search_success,
            search_error,
            compact_search_items,
            compact_pages,
        ) > max_context_chars:
            compact_pages.pop()

        while compact_search_items and self._workflow_context_length(
            query,
            search_success,
            search_error,
            compact_search_items,
            compact_pages,
        ) > max_context_chars:
            compact_search_items.pop()

        if self._workflow_context_length(
            query,
            search_success,
            search_error,
            compact_search_items,
            compact_pages,
        ) > max_context_chars:
            compact_pages = self._trim_page_contents_to_budget(
                query,
                search_success,
                search_error,
                compact_search_items,
                compact_pages,
                max_context_chars,
            )

        return compact_search_items, compact_pages

    def _compact_search_results(self, search_items: list[Any]) -> list[dict[str, Any]]:
        valid_items = [
            item
            for item in search_items
            if isinstance(item, dict) and self._is_valid_web_url(str(item.get("url") or "").strip())
        ]
        compact_items: list[dict[str, Any]] = []
        for item in sorted(valid_items, key=self._search_score, reverse=True)[:MAX_SEARCH_SUMMARY_RESULTS]:
            compact_items.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": self._truncate_text(
                        str(item.get("content") or item.get("snippet") or ""),
                        500,
                    ),
                    "snippet": self._truncate_text(str(item.get("snippet") or item.get("content") or ""), 500),
                    "score": item.get("score"),
                }
            )
        return compact_items

    def _compact_pages(self, pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        compact_pages: list[dict[str, Any]] = []
        for page in sorted(pages, key=self._search_score, reverse=True):
            compact_pages.append(
                {
                    "title": page.get("title", ""),
                    "url": page.get("url", ""),
                    "search_snippet": self._truncate_text(str(page.get("search_snippet") or ""), 500),
                    "score": page.get("score"),
                    "read_success": page.get("read_success"),
                    "read_error": page.get("read_error"),
                    "content": self._truncate_text(str(page.get("content") or ""), MAX_PAGE_CONTENT_CHARS),
                }
            )
        return compact_pages

    def _trim_page_contents_to_budget(
        self,
        query: str,
        search_success: bool,
        search_error: str | None,
        search_items: list[dict[str, Any]],
        pages: list[dict[str, Any]],
        max_context_chars: int,
    ) -> list[dict[str, Any]]:
        trimmed_pages = [dict(page) for page in pages]
        while trimmed_pages and self._workflow_context_length(
            query,
            search_success,
            search_error,
            search_items,
            trimmed_pages,
        ) > max_context_chars:
            longest_page = max(trimmed_pages, key=lambda page: len(str(page.get("content") or "")))
            content = str(longest_page.get("content") or "")
            if len(content) <= 500:
                trimmed_pages.pop()
                continue
            longest_page["content"] = self._truncate_text(content, max(len(content) - 500, 500))
        return trimmed_pages

    def _workflow_context_length(
        self,
        query: str,
        search_success: bool,
        search_error: str | None,
        search_items: list[dict[str, Any]],
        pages: list[dict[str, Any]],
    ) -> int:
        payload = {
            "query": query,
            "search_success": search_success,
            "search_error": search_error,
            "search_results": search_items,
            "read_pages": pages,
        }
        return len(json.dumps(payload, ensure_ascii=False))

    def _truncate_text(self, text: str, max_chars: int) -> str:
        cleaned = " ".join(text.split())
        if len(cleaned) <= max_chars:
            return cleaned
        if max_chars <= 3:
            return cleaned[:max_chars]
        return cleaned[: max_chars - 3].rstrip() + "..."

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
                arguments={
                    "query": user_message,
                    "max_results": DEFAULT_WEB_SEARCH_MAX_RESULTS,
                    "search_depth": "basic",
                },
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
                "你正在基于 web_search 返回的 Tavily 搜索结果回答用户问题。必须遵守："
                "1. 将搜索结果整理成自然语言回答，不要直接输出或复述 JSON；"
                "2. 只基于搜索结果回答，不编造搜索结果中没有的信息；"
                "3. 对多个来源进行交叉总结，合并重复信息，指出关键信息差异；"
                "4. 如果搜索结果不足、冲突或无法支持结论，要明确说明信息不足；"
                "5. 使用中文分点总结，结构清晰；"
                "6. 最后列出“参考来源”，来源格式必须是 [标题](URL)。"
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

        chinese_keywords = (
            "搜索",
            "查一下",
            "联网",
            "最新",
            "新闻",
            "资料",
            "官网",
            "最近",
            "价格",
            "github",
            "论文",
            "教程",
        )
        english_keywords = (
            "search",
            "latest",
            "news",
            "current",
            "recent",
            "github",
            "website",
            "official",
            "price",
        )
        extra_search_keywords = (
            "联网搜索",
            "网络搜索",
            "网上搜索",
            "帮我查",
            "项目",
            "today",
        )
        strong_keywords = chinese_keywords + english_keywords + extra_search_keywords
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
