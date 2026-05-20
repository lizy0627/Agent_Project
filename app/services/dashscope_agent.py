import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
import re
from time import perf_counter
from typing import Any, Iterator
from urllib.parse import urlsplit, urlunsplit

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
from app.core.safe_logging import safe_log_data, safe_log_field
from app.mcp.manager import MCPManager
from app.mcp.router import MCPRouter
from app.tools import create_default_tool_manager
from app.tools.base import ToolResult
from app.tools.tool_manager import MCP_SERVER_UNAVAILABLE, ToolManager


logger = get_logger(__name__)
ChatMessage = dict[str, str]
DEFAULT_WEB_SEARCH_MAX_RESULTS = 3
DEFAULT_SEARCH_WORKFLOW_READ_TOP_K = 2
MAX_SEARCH_WORKFLOW_READ_TOP_K = 2
WEB_SEARCH_TOOL_ARGUMENTS = {"query", "max_results", "search_depth"}
MAX_SEARCH_SUMMARY_RESULTS = 3
MAX_PAGE_SUMMARY_RESULTS = 2
MAX_PAGE_CONTENT_CHARS = 2500
MIN_PAGE_CONTENT_CHARS = 800
MAX_SEARCH_CONTEXT_CHARS = 8000
MAX_SEARCH_SNIPPET_CHARS = 500
NOISY_PAGE_KEYWORDS = (
    "广告",
    "推广",
    "赞助",
    "相关阅读",
    "相关推荐",
    "点击加载更多",
    "发表评论",
    "评论区",
    "advertisement",
    "advertising",
    "sponsored",
    "related articles",
    "recommended",
    "subscribe",
    "newsletter",
    "cookie policy",
)
MODELSCOPE_MCP_KEYWORDS = (
    "魔搭",
    "modelscope",
    "模型",
    "数据集",
    "dataset",
    "创空间",
    "论文",
    "paper",
    "mcp服务",
    "mcp 服务",
    "qwen",
    "通义千问",
)
MODELSCOPE_DEFAULT_TOOL_CANDIDATES = (
    "search",
    "modelscope_search",
    "search_models",
    "search_model",
    "model_search",
)
MODELSCOPE_QUERY_NOISE_PHRASES = (
    "相关模型",
    "模型",
    "搜索",
    "帮我",
    "魔搭",
    "关于",
)


def extract_search_keyword(query: str) -> str:
    """Extract the likely ModelScope search keyword from a Chinese request."""

    cleaned = " ".join(str(query or "").strip().split())
    if not cleaned:
        return ""

    patterns = (
        r"搜索\s*(?P<keyword>.+?)(?:相关模型|模型)?(?:[。！？?!，,；;]|$)",
        r"找\s*(?P<keyword>.+?)(?:相关模型|模型)(?:[。！？?!，,；;]|$)",
        r"关于\s*(?P<keyword>.+?)(?:相关模型|模型)?(?:[。！？?!，,；;]|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, cleaned, flags=re.IGNORECASE)
        if match:
            keyword = match.group("keyword").strip()
            if keyword:
                return keyword

    return cleaned


def normalize_query(query: str) -> str:
    """Normalize a ModelScope search query before sending it to MCP."""

    normalized = str(query or "").strip()
    if not normalized:
        return ""

    normalized = re.sub(
        r"\bqwen\s*-\s*(\d+)\b",
        lambda match: f"Qwen{match.group(1)}",
        normalized,
        flags=re.IGNORECASE,
    )
    for phrase in MODELSCOPE_QUERY_NOISE_PHRASES:
        normalized = normalized.replace(phrase, "")

    normalized = re.sub(r"(?i)\bmodelscope\b", "", normalized)
    normalized = re.sub(r"^[请麻烦帮忙我想要查找一下在上有关的\s]+", "", normalized)
    normalized = re.sub(r"[。！？?!，,；;：:\s]+$", "", normalized)
    normalized = " ".join(normalized.split())
    return normalized.strip()


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


@dataclass(frozen=True)
class SearchWorkflowPerformance:
    """Timing and page-count metrics for one search workflow run."""

    started_at: float
    search_seconds: float = 0.0
    reader_seconds: float = 0.0
    success_pages: int = 0
    failed_pages: int = 0
    cache_hit_count: int = 0


class DashScopeAgent:
    """Minimal agent that calls DashScope through the OpenAI-compatible API."""

    def __init__(self, settings: Settings, tool_manager: ToolManager | None = None) -> None:
        if not settings.dashscope_api_key:
            raise ApiKeyMissingError()

        self.settings = settings
        self.client = OpenAI(
            api_key=settings.dashscope_api_key,
            base_url=settings.dashscope_base_url,
            timeout=settings.dashscope_timeout_seconds,
        )
        self.model = settings.dashscope_model
        self.tool_manager = tool_manager or create_default_tool_manager(
            tavily_api_key=settings.tavily_api_key,
            web_search_provider=settings.web_search_provider,
            mcp_enabled=settings.mcp_enabled,
        )
        self.mcp_manager = MCPManager(
            timeout_seconds=settings.mcp_timeout_seconds,
            modelscope_url=settings.modelscope_mcp_url,
        )
        self.mcp_router = MCPRouter(self.mcp_manager)

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
            model_messages, workflow_result, performance = self._prepare_search_workflow(
                messages,
                planned_call,
            )
            logger.info("[SearchWorkflow] streaming summarize start")
            stream = self._stream_search_workflow_summary(
                model_messages,
                performance,
                model=model,
            )
            return stream, workflow_result

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
        logger.info(
            "EXEC_TOOL=%s ARGS=%s",
            planned_call.name if planned_call else None,
            safe_log_data(planned_call.arguments) if planned_call else None,
        )
        if planned_call is None:
            logger.info("No tool call needed for current user message")
            return None

        logger.info(
            "Executing planned tool: name=%s arguments=%s",
            planned_call.name,
            safe_log_data(planned_call.arguments),
        )
        if planned_call.name == "mcp_tool":
            return self._call_mcp_tool(planned_call)

        return self.tool_manager.call(planned_call.name, **planned_call.arguments)

    def _log_planned_tool(self, planned_call: PlannedToolCall) -> None:
        logger.info(
            "PLANNED_TOOL=%s ARGS=%s",
            planned_call.name,
            safe_log_data(planned_call.arguments),
        )

    def _safe_planned_tool_log(self, planned_call: PlannedToolCall | None) -> dict[str, Any] | None:
        if planned_call is None:
            return None
        return {
            "name": planned_call.name,
            "arguments": safe_log_data(planned_call.arguments),
        }

    def _call_mcp_tool(self, planned_call: PlannedToolCall) -> ToolResult:
        original_query = str(planned_call.arguments.get("original_query") or "")
        rewritten_query = str(planned_call.arguments.get("rewritten_query") or "")
        fallback_queries = planned_call.arguments.get("query_fallbacks")
        if not isinstance(fallback_queries, list) or not fallback_queries:
            fallback_queries = [rewritten_query or original_query]

        mcp_arguments = planned_call.arguments.get("arguments")
        base_mcp_arguments = mcp_arguments if isinstance(mcp_arguments, dict) else {}
        call_base = {
            key: value
            for key, value in planned_call.arguments.items()
            if key not in {
                "arguments",
                "original_query",
                "rewritten_query",
                "query_fallbacks",
                "route_reason",
            }
        }

        last_result: ToolResult | None = None
        final_query = str(fallback_queries[0] or "")
        for index, query in enumerate(fallback_queries):
            query_text = str(query or "").strip()
            call_arguments = dict(call_base)
            call_arguments["arguments"] = self._with_mcp_query_arguments(base_mcp_arguments, query_text)
            last_result = self.tool_manager.call(planned_call.name, **call_arguments)
            last_result = self._normalize_mcp_tool_result(last_result)
            final_query = query_text

            if not self._is_empty_mcp_result(last_result):
                break
            if index < len(fallback_queries) - 1:
                logger.info(
                    "MCP result empty, fallback query: %s",
                    safe_log_field("query", fallback_queries[index + 1]),
                )

        if last_result is None:
            last_result = self.tool_manager.call(planned_call.name, **planned_call.arguments)
            last_result = self._normalize_mcp_tool_result(last_result)

        return self._with_mcp_query_metadata(
            last_result,
            original_query=original_query,
            rewritten_query=rewritten_query,
            final_query=final_query,
            route_reason=str(planned_call.arguments.get("route_reason") or ""),
        )

    def _normalize_mcp_tool_result(self, tool_result: ToolResult) -> ToolResult:
        if tool_result.name != "mcp_tool" or not isinstance(tool_result.result, dict):
            return tool_result
        if tool_result.result.get("success") is not False:
            return tool_result

        return ToolResult(
            name=tool_result.name,
            success=False,
            result=tool_result.result,
            error=str(tool_result.result.get("error") or "MCP tool call failed."),
            duration_ms=tool_result.duration_ms,
            error_code=tool_result.error_code or MCP_SERVER_UNAVAILABLE,
            error_message=tool_result.error_message
            or str(tool_result.result.get("error") or "MCP tool call failed."),
            retryable=tool_result.retryable,
        )

    def _is_modelscope_mcp_call(self, planned_call: PlannedToolCall) -> bool:
        return (
            planned_call.name == "mcp_tool"
            and str(planned_call.arguments.get("server_name") or "").strip().lower() == "modelscope"
        )

    def _call_modelscope_mcp_tool(self, planned_call: PlannedToolCall) -> ToolResult:
        original_query = str(planned_call.arguments.get("original_query") or "")
        rewritten_query = str(planned_call.arguments.get("rewritten_query") or "")
        mcp_arguments = planned_call.arguments.get("arguments")
        base_mcp_arguments = mcp_arguments if isinstance(mcp_arguments, dict) else {}
        fallback_queries = self._modelscope_query_fallbacks(rewritten_query)
        if not fallback_queries:
            fallback_queries = [rewritten_query or original_query]

        logger.info("原问题: %s", safe_log_field("original_query", original_query))
        logger.info("重写后: %s", safe_log_field("rewritten_query", rewritten_query))

        last_result: ToolResult | None = None
        final_query = fallback_queries[0]
        for index, query in enumerate(fallback_queries):
            query_arguments = self._with_mcp_query_arguments(base_mcp_arguments, query)
            call_arguments = {
                key: value
                for key, value in planned_call.arguments.items()
                if key not in {"arguments", "original_query", "rewritten_query"}
            }
            call_arguments["arguments"] = query_arguments
            last_result = self.tool_manager.call(planned_call.name, **call_arguments)
            final_query = query

            if not self._is_empty_modelscope_mcp_result(last_result):
                break
            if index < len(fallback_queries) - 1:
                logger.info(
                    "ModelScope MCP result empty, fallback query: %s",
                    safe_log_field("query", fallback_queries[index + 1]),
                )

        logger.info("降级后: %s", safe_log_field("query", final_query))
        if last_result is not None:
            return self._with_modelscope_query_metadata(
                last_result,
                original_query=original_query,
                rewritten_query=rewritten_query,
                final_query=final_query,
            )

        return self.tool_manager.call(planned_call.name, **planned_call.arguments)

    def _handle_search_workflow(
        self,
        messages: list[ChatMessage],
        planned_call: PlannedToolCall,
        model: str | None = None,
    ) -> AgentReply:
        """Run search, read top pages, and ask the model to synthesize an answer."""

        model_messages, workflow_result, performance = self._prepare_search_workflow(
            messages,
            planned_call,
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
        self._log_search_workflow_performance(
            performance,
            llm_seconds=self._elapsed_seconds(summarize_started_at),
        )
        return AgentReply(content=reply, tool_result=workflow_result)

    def _prepare_search_workflow_messages(
        self,
        messages: list[ChatMessage],
        planned_call: PlannedToolCall,
    ) -> tuple[list[ChatMessage], ToolResult]:
        """Run the search workflow and return model messages ready for final synthesis."""

        model_messages, workflow_result, _performance = self._prepare_search_workflow(
            messages,
            planned_call,
        )
        return model_messages, workflow_result

    def _prepare_search_workflow(
        self,
        messages: list[ChatMessage],
        planned_call: PlannedToolCall,
    ) -> tuple[list[ChatMessage], ToolResult, SearchWorkflowPerformance]:
        """Prepare search context and collect performance metrics."""

        workflow_started_at = perf_counter()
        user_message = self._latest_user_message(messages)
        query = str(planned_call.arguments.get("query", user_message))
        search_kwargs = self._web_search_tool_arguments(planned_call.arguments, query=query)
        should_read_pages = self._should_read_web_pages(user_message or query)
        read_top_k = min(
            self._positive_int(
                planned_call.arguments.get("read_top_k"),
                default=DEFAULT_SEARCH_WORKFLOW_READ_TOP_K,
            ),
            MAX_SEARCH_WORKFLOW_READ_TOP_K,
        )
        logger.info("Search workflow started: query=%s", safe_log_field("query", query))
        search_started_at = perf_counter()
        search_result = self._call_search_workflow_tool("web_search", **search_kwargs)
        search_cost = self._elapsed_seconds(search_started_at)
        workflow_step_results = [search_result]
        cache_hit_count = 1 if self._is_cache_hit(search_result) else 0
        search_payload = search_result.result if isinstance(search_result.result, dict) else {}
        search_items = search_payload.get("results", []) if search_result.success else []
        search_result_count = len(search_items) if isinstance(search_items, list) else 0
        logger.info(
            "Search workflow web_search finished: success=%s result_count=%s error=%s cost=%.2fs",
            search_result.success,
            search_result_count,
            search_result.error,
            search_cost,
        )

        pages: list[dict[str, Any]] = []
        reader_cost = 0.0
        selected_page_count = 0
        successful_reader_count = 0
        if should_read_pages:
            logger.info("[SearchWorkflow] read web pages because deep analysis query")
        else:
            logger.info("[SearchWorkflow] skip web_reader because simple search query")

        if should_read_pages and isinstance(search_items, list):
            selected_items = self._select_search_items_for_reading(search_items, read_top_k)
            selected_page_count = len(selected_items)
            logger.info(
                "Search workflow selected pages for reading: requested=%s selected=%s",
                read_top_k,
                len(selected_items),
            )
            reader_started_at = perf_counter()
            reader_pairs = self._read_search_pages_concurrently(selected_items)
            reader_cost = self._elapsed_seconds(reader_started_at)
            logger.info(
                "Search workflow web_reader total finished: selected=%s returned=%s cost=%.2fs",
                len(selected_items),
                len(reader_pairs),
                reader_cost,
            )
            for item, reader_result in reader_pairs:
                workflow_step_results.append(reader_result)
                if self._is_cache_hit(reader_result):
                    cache_hit_count += 1
                if not reader_result.success:
                    logger.warning(
                        "Search workflow web_reader failed, skipped: url=%s error=%s",
                        safe_log_field("url", str(item.get("url") or "").strip()),
                        reader_result.error,
                    )
                    continue

                successful_reader_count += 1
                url = str(item.get("url") or "").strip()
                logger.info(
                    "Search workflow web_reader finished: url=%s success=%s error=%s",
                    safe_log_field("url", url),
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
            web_pages_read=should_read_pages,
        )
        workflow_payload = {
            "query": query,
            "search_success": search_result.success,
            "search_error": search_result.error,
            "search_results": compact_search_items,
            "read_pages": compact_pages,
            "web_pages_read": should_read_pages,
            "context_limited": self._is_search_context_limited(
                search_result_count=search_result_count,
                compact_search_count=len(compact_search_items),
                raw_page_count=len(pages),
                compact_page_count=len(compact_pages),
                web_pages_read=should_read_pages,
            ),
            "context_note": (
                "搜索结果有限；如果材料不足以支持结论，请在最终回答中明确说明。"
            ),
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
            error_code=search_result.error_code,
            error_message=search_result.error_message,
            retryable=search_result.retryable,
        )
        model_messages = self._messages_with_search_workflow_result(messages, workflow_result)
        logger.info(
            "Search workflow summary prepared: search_success=%s read_pages=%s successful_reads=%s",
            search_result.success,
            len(pages),
            sum(1 for page in pages if page.get("read_success")),
        )
        performance = SearchWorkflowPerformance(
            started_at=workflow_started_at,
            search_seconds=search_cost,
            reader_seconds=reader_cost,
            success_pages=successful_reader_count,
            failed_pages=max(selected_page_count - successful_reader_count, 0),
            cache_hit_count=cache_hit_count,
        )
        return model_messages, workflow_result, performance

    def _stream_search_workflow_summary(
        self,
        messages: list[ChatMessage],
        performance: SearchWorkflowPerformance,
        model: str | None = None,
    ) -> Iterator[str]:
        summarize_started_at = perf_counter()
        try:
            yield from self._stream_complete_chat(messages, model=model)
        finally:
            llm_seconds = self._elapsed_seconds(summarize_started_at)
            logger.info("[SearchWorkflow] streaming summarize done, cost=%.2fs", llm_seconds)
            self._log_search_workflow_performance(performance, llm_seconds=llm_seconds)

    def _log_search_workflow_performance(
        self,
        performance: SearchWorkflowPerformance,
        llm_seconds: float,
    ) -> None:
        logger.info(
            (
                "[SearchWorkflow] total=%.2fs search=%.2fs reader=%.2fs llm=%.2fs "
                "success_pages=%s failed_pages=%s cache_hits=%s"
            ),
            self._elapsed_seconds(performance.started_at),
            performance.search_seconds,
            performance.reader_seconds,
            llm_seconds,
            performance.success_pages,
            performance.failed_pages,
            performance.cache_hit_count,
        )

    def _call_search_workflow_tool(self, name: str, **kwargs: Any) -> ToolResult:
        started_at = perf_counter()
        safe_kwargs = safe_log_data(kwargs)
        url = str(safe_kwargs.get("url") or "").strip() if isinstance(safe_kwargs, dict) else ""
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
            "Search workflow step finished: tool_name=%s success=%s duration_ms=%s error_code=%s",
            result.name,
            result.success,
            result.duration_ms,
            result.error_code,
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
                    safe_log_field("url", url),
                    result,
                )
                continue
            reader_pairs.append((item, result))
        return reader_pairs

    def _sum_tool_durations(self, results: list[ToolResult]) -> float:
        return round(sum(result.duration_ms or 0 for result in results), 2)

    def _is_cache_hit(self, result: ToolResult) -> bool:
        return isinstance(result.result, dict) and result.result.get("cached") is True

    def _elapsed_seconds(self, started_at: float) -> float:
        return round(perf_counter() - started_at, 2)

    def _web_search_tool_arguments(self, arguments: dict[str, Any], query: str) -> dict[str, Any]:
        tool_arguments = {
            key: value for key, value in arguments.items() if key in WEB_SEARCH_TOOL_ARGUMENTS
        }
        tool_arguments["query"] = query
        tool_arguments.setdefault("max_results", DEFAULT_WEB_SEARCH_MAX_RESULTS)
        tool_arguments["max_results"] = min(
            self._positive_int(tool_arguments.get("max_results"), DEFAULT_WEB_SEARCH_MAX_RESULTS),
            MAX_SEARCH_SUMMARY_RESULTS,
        )
        tool_arguments.setdefault("search_depth", "basic")
        return tool_arguments

    def _select_search_items_for_reading(
        self,
        search_items: list[Any],
        read_top_k: int,
    ) -> list[dict[str, Any]]:
        valid_items = self._dedupe_search_items_by_url(search_items)
        return sorted(valid_items, key=self._search_score, reverse=True)[:read_top_k]

    def _is_valid_web_url(self, url: str) -> bool:
        return url.lower().startswith(("http://", "https://"))

    def _normalize_url_for_dedupe(self, url: str) -> str:
        clean_url = url.strip()
        if not clean_url:
            return ""
        try:
            parts = urlsplit(clean_url)
        except ValueError:
            return clean_url.lower()
        path = parts.path or "/"
        return urlunsplit(
            (
                parts.scheme.lower(),
                parts.netloc.lower(),
                path.rstrip("/") or "/",
                parts.query,
                "",
            )
        )

    def _dedupe_search_items_by_url(self, search_items: list[Any]) -> list[dict[str, Any]]:
        best_by_url: dict[str, dict[str, Any]] = {}
        for item in search_items:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            if not self._is_valid_web_url(url):
                continue
            normalized_url = self._normalize_url_for_dedupe(url)
            existing = best_by_url.get(normalized_url)
            if existing is None or self._search_score(item) > self._search_score(existing):
                best_by_url[normalized_url] = item
        return list(best_by_url.values())

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
        web_pages_read: bool,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        compact_search_items = self._compact_search_results(search_items)
        compact_pages = self._compact_pages(pages)

        while self._workflow_context_length(
            query,
            search_success,
            search_error,
            compact_search_items,
            compact_pages,
            web_pages_read,
        ) > max_context_chars:
            if self._trim_longest_page_content(compact_pages):
                continue
            if compact_pages:
                compact_pages.pop()
                continue
            if compact_search_items:
                compact_search_items.pop()
                continue
            break

        return compact_search_items, compact_pages

    def _compact_search_results(self, search_items: list[Any]) -> list[dict[str, Any]]:
        valid_items = self._dedupe_search_items_by_url(search_items)
        compact_items: list[dict[str, Any]] = []
        for item in sorted(valid_items, key=self._search_score, reverse=True)[:MAX_SEARCH_SUMMARY_RESULTS]:
            snippet = self._compact_search_snippet(item)
            compact_items.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": snippet,
                    "snippet": snippet,
                    "score": item.get("score"),
                }
            )
        return compact_items

    def _compact_pages(self, pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        compact_pages: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        for page in sorted(pages, key=self._search_score, reverse=True):
            if len(compact_pages) >= MAX_PAGE_SUMMARY_RESULTS:
                break
            if not page.get("read_success"):
                continue
            url = str(page.get("url") or "").strip()
            normalized_url = self._normalize_url_for_dedupe(url)
            if not normalized_url or normalized_url in seen_urls:
                continue
            content = self._extract_leading_page_context(str(page.get("content") or ""))
            if not content:
                continue
            seen_urls.add(normalized_url)
            compact_pages.append(
                {
                    "title": page.get("title", ""),
                    "url": url,
                    "search_snippet": self._truncate_text(
                        self._remove_noisy_text(str(page.get("search_snippet") or "")),
                        MAX_SEARCH_SNIPPET_CHARS,
                    ),
                    "score": page.get("score"),
                    "content": content,
                }
            )
        return compact_pages

    def _compact_search_snippet(self, item: dict[str, Any]) -> str:
        text = str(item.get("content") or item.get("snippet") or "")
        return self._truncate_text(self._remove_noisy_text(text), MAX_SEARCH_SNIPPET_CHARS)

    def _extract_leading_page_context(self, content: str) -> str:
        clean_content = content.strip()
        if not clean_content:
            return ""

        paragraphs: list[str] = []
        seen: set[str] = set()
        for raw_paragraph in re.split(r"\n{2,}|\r\n{2,}", clean_content):
            paragraph = " ".join(raw_paragraph.split())
            if not paragraph:
                continue
            if self._looks_like_noisy_text(paragraph):
                continue
            normalized = paragraph.casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            paragraphs.append(paragraph)
            if len(" ".join(paragraphs)) >= MAX_PAGE_CONTENT_CHARS:
                break

        return self._truncate_text("\n\n".join(paragraphs), MAX_PAGE_CONTENT_CHARS)

    def _remove_noisy_text(self, text: str) -> str:
        cleaned_parts = [
            part
            for part in (" ".join(chunk.split()) for chunk in re.split(r"\n+|。|；|;", text))
            if part and not self._looks_like_noisy_text(part)
        ]
        return " ".join(cleaned_parts)

    def _looks_like_noisy_text(self, text: str) -> bool:
        lowered = text.lower()
        if any(keyword in lowered for keyword in NOISY_PAGE_KEYWORDS):
            return True
        if len(text) <= 20 and re.search(r"(登录|注册|分享|收藏|评论|subscribe|sign in)", lowered):
            return True
        return False

    def _trim_longest_page_content(self, pages: list[dict[str, Any]]) -> bool:
        trim_candidates = [
            page
            for page in pages
            if len(str(page.get("content") or "")) > MIN_PAGE_CONTENT_CHARS
        ]
        if not trim_candidates:
            return False

        longest_page = max(trim_candidates, key=lambda page: len(str(page.get("content") or "")))
        content = str(longest_page.get("content") or "")
        longest_page["content"] = self._truncate_text(
            content,
            max(len(content) - 500, MIN_PAGE_CONTENT_CHARS),
        )
        return True

    def _is_search_context_limited(
        self,
        search_result_count: int,
        compact_search_count: int,
        raw_page_count: int,
        compact_page_count: int,
        web_pages_read: bool,
    ) -> bool:
        return (
            search_result_count == 0
            or compact_search_count < search_result_count
            or (
                web_pages_read
                and (
                    raw_page_count == 0
                    or compact_page_count == 0
                    or compact_page_count < raw_page_count
                )
            )
        )

    def _workflow_context_length(
        self,
        query: str,
        search_success: bool,
        search_error: str | None,
        search_items: list[dict[str, Any]],
        pages: list[dict[str, Any]],
        web_pages_read: bool,
    ) -> int:
        payload = {
            "query": query,
            "search_success": search_success,
            "search_error": search_error,
            "search_results": search_items,
            "read_pages": pages,
            "web_pages_read": web_pages_read,
            "context_limited": False,
            "context_note": (
                "搜索结果有限；如果材料不足以支持结论，请在最终回答中明确说明。"
            ),
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
        logger.info("USER=%s", safe_log_field("user_message", user_message))
        logger.info("USER_MESSAGE=%s", safe_log_field("user_message", user_message))
        if not user_message:
            return None

        planned_call: PlannedToolCall | None = None
        if self._looks_like_time_request(user_message):
            planned_call = PlannedToolCall(
                name="get_current_time",
                arguments={"timezone": "Asia/Shanghai"},
            )
        else:
            expression = self._extract_calculation_expression(user_message)
            if expression:
                planned_call = PlannedToolCall(
                    name="calculate",
                    arguments={"expression": expression},
                )

        if planned_call is None:
            mcp_call = self._plan_mcp_tool(user_message)
            logger.info("ROUTE=%s", self._safe_planned_tool_log(mcp_call))
            if mcp_call:
                planned_call = mcp_call

        if planned_call is None:
            text_to_summarize = self._extract_text_to_summarize(user_message)
            if text_to_summarize:
                planned_call = PlannedToolCall(
                    name="summarize_text",
                    arguments={"text": text_to_summarize},
                )

        if planned_call is None and self._looks_like_search_request(user_message):
            planned_call = PlannedToolCall(
                name="web_search",
                arguments={
                    "query": user_message,
                    "max_results": DEFAULT_WEB_SEARCH_MAX_RESULTS,
                    "search_depth": "basic",
                },
            )

        if planned_call:
            logger.info("SELECTED=%s", planned_call.name)
            self._log_planned_tool(planned_call)
        return planned_call

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
            "error_code": tool_result.error_code,
            "error_message": tool_result.error_message,
            "retryable": tool_result.retryable,
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

        if tool_result.name == "mcp_tool":
            mcp_system_prompt = """
你正在基于 MCP 工具返回结果回答。

绝对规则：

1. 先检查 JSON:

success=true / false

2. 如果 success=true：

说明工具调用成功。

严禁输出：

* MCP SDK未安装
* 请执行 pip install
* MCP失败
* Server未启动

除非 error 字段真实包含这些内容。

3. success=true 时：

必须基于 result.data 内容回答。

4. success=false 时：

只能复述 error 字段。

禁止编造错误。

5. 不要猜测失败原因。

6. 不要复述 JSON。

7. 使用中文。

"""
            tool_execution_status = (
                "工具调用成功"
                if tool_result.success
                else "工具调用失败"
            )
            tool_context = f"""
状态:

{tool_execution_status}

工具结果:

{json.dumps(payload,ensure_ascii=False)}

请回答原问题。
"""
            return [
                *messages,
                {
                    "role": "system",
                    "content": mcp_system_prompt,
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

    def _plan_mcp_tool(self, user_message: str) -> PlannedToolCall | None:
        if not self.settings.mcp_enabled:
            return None

        route = self.mcp_router.route(user_message)
        if not route:
            return None

        planned_call = PlannedToolCall(
            name="mcp_tool",
            arguments={
                "server_name": route["server_name"],
                "tool_name": route["tool_name"],
                "arguments": route.get("arguments") or {},
                "original_query": route.get("original_query") or user_message,
                "rewritten_query": route.get("rewritten_query") or "",
                "query_fallbacks": route.get("query_fallbacks") or [],
                "route_reason": route.get("reason") or "",
            },
        )
        self._log_planned_tool(planned_call)
        return planned_call

    def _plan_modelscope_mcp_tool(self, user_message: str) -> PlannedToolCall | None:
        if not self.settings.mcp_enabled:
            return None
        if not self._looks_like_modelscope_mcp_request(user_message):
            return None

        server_name = self.settings.mcp_default_server or "modelscope"
        tool = self._select_modelscope_tool(user_message, server_name)
        tool_name = str(tool.get("name") or "").strip()
        if not tool_name:
            tool_name = MODELSCOPE_DEFAULT_TOOL_CANDIDATES[0]

        rewritten_query = normalize_query(extract_search_keyword(user_message)) or normalize_query(user_message)
        arguments = self._build_mcp_tool_arguments(user_message, tool, rewritten_query)
        planned_call = PlannedToolCall(
            name="mcp_tool",
            arguments={
                "server_name": server_name,
                "tool_name": tool_name,
                "arguments": arguments,
                "original_query": user_message,
                "rewritten_query": rewritten_query,
            },
        )
        self._log_planned_tool(planned_call)
        return planned_call

    def _looks_like_modelscope_mcp_request(self, message: str) -> bool:
        lowered = message.lower()
        return any(keyword.lower() in lowered for keyword in MODELSCOPE_MCP_KEYWORDS)

    def _select_modelscope_tool(self, user_message: str, server_name: str) -> dict[str, Any]:
        try:
            manager = MCPManager(
                timeout_seconds=self.settings.mcp_timeout_seconds,
                modelscope_url=self.settings.modelscope_mcp_url,
            )
            list_result = manager.client.list_tools(server_name)
        except Exception as exc:
            logger.warning("ModelScope MCP list_tools planning failed: %s", exc)
            return {"name": MODELSCOPE_DEFAULT_TOOL_CANDIDATES[0]}

        if not list_result.get("success"):
            logger.warning("ModelScope MCP list_tools failed: error=%s", list_result.get("error"))
            return {"name": MODELSCOPE_DEFAULT_TOOL_CANDIDATES[0]}

        tools = (list_result.get("data") or {}).get("tools", [])
        if not isinstance(tools, list) or not tools:
            logger.warning("ModelScope MCP server returned no tools during planning")
            return {"name": MODELSCOPE_DEFAULT_TOOL_CANDIDATES[0]}

        selected_tool = max(
            [tool for tool in tools if isinstance(tool, dict)],
            key=lambda tool: self._modelscope_tool_score(user_message, tool),
            default={},
        )
        logger.info(
            "ModelScope MCP tool selected: tool=%s",
            selected_tool.get("name") if isinstance(selected_tool, dict) else "",
        )
        return selected_tool if isinstance(selected_tool, dict) else {}

    def _modelscope_tool_score(self, user_message: str, tool: dict[str, Any]) -> int:
        lowered_message = user_message.lower()
        tool_name = str(tool.get("name") or "").lower()
        description = str(tool.get("description") or "").lower()
        searchable = f"{tool_name} {description}"
        score = 0

        if "search" in searchable or "搜索" in searchable:
            score += 20
        if any(candidate in tool_name for candidate in MODELSCOPE_DEFAULT_TOOL_CANDIDATES):
            score += 12
        if any(keyword in lowered_message for keyword in ("模型", "model", "qwen", "通义千问")):
            score += self._category_score(searchable, ("model", "模型"))
        if any(keyword in lowered_message for keyword in ("数据集", "dataset")):
            score += self._category_score(searchable, ("dataset", "数据集"))
        if any(keyword in lowered_message for keyword in ("创空间", "space", "studio")):
            score += self._category_score(searchable, ("space", "创空间", "studio"))
        if any(keyword in lowered_message for keyword in ("论文", "paper")):
            score += self._category_score(searchable, ("paper", "论文"))
        if "mcp" in lowered_message:
            score += self._category_score(searchable, ("mcp", "服务"))

        return score

    def _category_score(self, searchable: str, category_keywords: tuple[str, ...]) -> int:
        return 10 if any(keyword in searchable for keyword in category_keywords) else 0

    def _build_mcp_tool_arguments(
        self,
        user_message: str,
        tool: dict[str, Any],
        rewritten_query: str | None = None,
    ) -> dict[str, Any]:
        input_schema = tool.get("inputSchema") or tool.get("input_schema") or {}
        properties = input_schema.get("properties", {}) if isinstance(input_schema, dict) else {}
        query = rewritten_query or normalize_query(extract_search_keyword(user_message)) or user_message
        if not isinstance(properties, dict) or not properties:
            return {"query": query}

        arguments: dict[str, Any] = {}
        for property_name, property_schema in properties.items():
            lowered_name = str(property_name).lower()
            if self._looks_like_query_argument(lowered_name):
                arguments[property_name] = query
                continue
            if self._looks_like_limit_argument(lowered_name):
                arguments[property_name] = 5
                continue

            default_value = self._schema_default_value(property_schema)
            if default_value is not None:
                arguments[property_name] = default_value

        required = input_schema.get("required", []) if isinstance(input_schema, dict) else []
        if isinstance(required, list):
            for property_name in required:
                if property_name not in arguments:
                    arguments[property_name] = query

        if not arguments:
            arguments["query"] = query
        return arguments

    def _with_mcp_query_arguments(self, arguments: dict[str, Any], query: str) -> dict[str, Any]:
        updated = dict(arguments)
        url_keys = [
            key
            for key in updated
            if "url" in str(key).lower()
        ]
        if url_keys:
            for key in url_keys:
                updated[key] = query
            return updated

        query_keys = [
            key
            for key in updated
            if self._looks_like_query_argument(str(key).lower())
        ]
        if not query_keys:
            updated["query"] = query
            return updated

        for key in query_keys:
            updated[key] = query
        return updated

    def _modelscope_query_fallbacks(self, query: str) -> list[str]:
        normalized = normalize_query(query)
        candidates = [normalized] if normalized else []
        if normalized.lower() == "qwen3":
            candidates.extend(["Qwen", "Qwen2"])
        return self._dedupe_nonempty(candidates)

    def _dedupe_nonempty(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for value in values:
            cleaned = value.strip()
            if not cleaned:
                continue
            key = cleaned.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(cleaned)
        return deduped

    def _with_modelscope_query_metadata(
        self,
        tool_result: ToolResult,
        original_query: str,
        rewritten_query: str,
        final_query: str,
    ) -> ToolResult:
        if isinstance(tool_result.result, dict):
            result = dict(tool_result.result)
            server_name = str(result.get("server_name") or "")
            server = self.mcp_manager.get_server(server_name) if server_name else None
            if server and server.url:
                result["server_url"] = server.url
            result["query_rewrite"] = {
                "original": original_query,
                "rewritten": rewritten_query,
                "final": final_query,
            }
        else:
            result = tool_result.result

        return ToolResult(
            name=tool_result.name,
            success=tool_result.success,
            result=result,
            error=tool_result.error,
            duration_ms=tool_result.duration_ms,
            error_code=tool_result.error_code,
            error_message=tool_result.error_message,
            retryable=tool_result.retryable,
        )

    def _with_mcp_query_metadata(
        self,
        tool_result: ToolResult,
        original_query: str,
        rewritten_query: str,
        final_query: str,
        route_reason: str,
    ) -> ToolResult:
        if isinstance(tool_result.result, dict):
            result = dict(tool_result.result)
            server_name = str(result.get("server_name") or "")
            server = self.mcp_manager.get_server(server_name) if server_name else None
            if server and server.url:
                result["server_url"] = server.url
            result["query_rewrite"] = {
                "original": original_query,
                "rewritten": rewritten_query,
                "final": final_query,
            }
            if route_reason:
                result["route_reason"] = route_reason
        else:
            result = tool_result.result

        return ToolResult(
            name=tool_result.name,
            success=tool_result.success,
            result=result,
            error=tool_result.error,
            duration_ms=tool_result.duration_ms,
            error_code=tool_result.error_code,
            error_message=tool_result.error_message,
            retryable=tool_result.retryable,
        )

    def _is_empty_mcp_result(self, tool_result: ToolResult) -> bool:
        if not tool_result.success:
            return False
        if isinstance(tool_result.result, dict) and tool_result.result.get("success") is False:
            return False
        status = self._modelscope_collection_status(tool_result.result)
        return status is False

    def _is_empty_modelscope_mcp_result(self, tool_result: ToolResult) -> bool:
        if not tool_result.success:
            return False
        if isinstance(tool_result.result, dict) and tool_result.result.get("success") is False:
            return False

        status = self._modelscope_collection_status(tool_result.result)
        return status is False

    def _modelscope_collection_status(self, value: Any, from_collection_key: bool = False) -> bool | None:
        parsed_value = self._parse_json_if_possible(value)
        if parsed_value is not value:
            return self._modelscope_collection_status(parsed_value, from_collection_key=from_collection_key)

        if isinstance(value, dict):
            for key in ("result", "results", "models", "model_list", "items"):
                if key in value:
                    status = self._modelscope_collection_status(value[key], from_collection_key=True)
                    if status is not None:
                        return status

            for key in ("structuredContent", "structured_content", "data", "content", "text"):
                if key in value:
                    status = self._modelscope_collection_status(value[key])
                    if status is not None:
                        return status
            return None

        if isinstance(value, list):
            if not value:
                return False

            child_statuses = [
                self._modelscope_collection_status(item)
                for item in value
            ]
            if any(status is True for status in child_statuses):
                return True
            if any(status is False for status in child_statuses):
                return False
            return True if from_collection_key else None

        return None

    def _parse_json_if_possible(self, value: Any) -> Any:
        if not isinstance(value, str):
            return value

        stripped = value.strip()
        if not stripped or stripped[0] not in "[{":
            return value

        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return value

    def _looks_like_query_argument(self, name: str) -> bool:
        query_keywords = ("query", "keyword", "keywords", "search", "q", "text", "name")
        return any(keyword in name for keyword in query_keywords)

    def _looks_like_limit_argument(self, name: str) -> bool:
        limit_keywords = ("limit", "count", "size", "page_size", "max_results", "top_k")
        return any(keyword in name for keyword in limit_keywords)

    def _schema_default_value(self, schema: Any) -> Any:
        if not isinstance(schema, dict):
            return None
        if "default" in schema:
            return schema["default"]
        if "enum" in schema and isinstance(schema["enum"], list) and schema["enum"]:
            return schema["enum"][0]
        return None

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
            "error_code": tool_result.error_code,
            "error_message": tool_result.error_message,
            "retryable": tool_result.retryable,
        }
        search_system_prompt = (
            "你是一个严谨的联网研究助手。你已经获得 Tavily 搜索摘要；"
            "对需要深度分析的问题，JSON 中还可能包含前几个网页的正文摘录。"
            "请只基于这些材料回答用户最初的问题，不要编造材料中没有的信息。"
            "需要对多个来源进行交叉总结，合并重复信息，并说明材料中的差异或不确定性。"
            "如果 JSON 中 read_pages 为空，请只基于 search_results 中的 title、url、content/snippet 总结。"
            "如果 JSON 中 context_limited 为 true，或搜索、网页读取信息不足，要明确说明哪些结论无法确认。"
            "最终回答必须使用中文，并包含以下四个部分："
            "一、结论；二、关键要点；三、详细解释；四、参考来源。"
            "参考来源必须使用 Markdown 链接格式：[标题](URL)。"
        )
        tool_context = (
            "已完成联网搜索工作流：用户问题 -> Tavily 搜索 -> 按需读取网页 -> 汇总材料。"
            "请基于下面 JSON 中的搜索摘要和可用网页正文生成最终回答。\n"
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

    def _should_read_web_pages(self, message: str) -> bool:
        """Return True when search snippets are unlikely to be enough."""

        lowered = message.lower().strip()
        if not lowered:
            return False

        if re.search(r"https?://\S+|www\.\S+|\b[a-z0-9][a-z0-9.-]*\.[a-z]{2,}(?:/\S*)?", lowered):
            return True

        deep_analysis_keywords = (
            "详细分析",
            "详细解析",
            "深入",
            "深度",
            "deep analysis",
            "in-depth",
            "in depth",
        )
        if any(keyword in lowered for keyword in deep_analysis_keywords):
            return True

        article_summary_keywords = (
            "总结这篇文章",
            "总结这篇",
            "总结文章",
            "summarize this article",
        )
        if any(keyword in lowered for keyword in article_summary_keywords):
            return True

        github_project_keywords = (
            "github项目",
            "github 项目",
            "github仓库",
            "github 仓库",
            "github repo",
            "github repository",
        )
        if any(keyword in lowered for keyword in github_project_keywords):
            return True
        if "github" in lowered and any(
            keyword in lowered for keyword in ("分析", "解析", "项目", "仓库", "源码", "repo", "repository")
        ):
            return True

        organize_keywords = ("整理", "汇总", "收集", "梳理", "归纳", "compile", "collect")
        technical_material_keywords = (
            "技术资料",
            "技术文档",
            "论文",
            "教程",
            "paper",
            "papers",
            "tutorial",
            "tutorials",
        )
        return any(keyword in lowered for keyword in organize_keywords) and any(
            keyword in lowered for keyword in technical_material_keywords
        )

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
