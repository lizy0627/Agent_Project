import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import re
from time import perf_counter
from typing import Any, Iterator
from urllib.parse import urlsplit, urlunsplit

from app.core.logger import get_logger
from app.core.safe_logging import safe_log_data, safe_log_field
from app.services.agent_planner import DEFAULT_WEB_SEARCH_MAX_RESULTS, WEB_SEARCH_ROUTE_REASON, PlannedToolCall
from app.services.agent_types import (
    ChatMessage,
    DEFAULT_SEARCH_WORKFLOW_READ_TOP_K,
    MAX_PAGE_CONTENT_CHARS,
    MAX_PAGE_SUMMARY_RESULTS,
    MAX_SEARCH_CONTEXT_CHARS,
    MAX_SEARCH_SNIPPET_CHARS,
    MAX_SEARCH_SUMMARY_RESULTS,
    MAX_SEARCH_WORKFLOW_READ_TOP_K,
    MIN_PAGE_CONTENT_CHARS,
    NOISY_PAGE_KEYWORDS,
    SearchWorkflowPerformance,
    StatusCallback,
    STATUS_WEB_READING,
    WEB_SEARCH_TOOL_ARGUMENTS,
)
from app.services.message_builder import MessageBuilder
from app.tools.base import ToolResult
from app.tools.tool_manager import ToolManager


logger = get_logger(__name__)


class SearchWorkflow:
    """Run web_search, optionally read pages, and build compact search context."""

    def __init__(self, tool_manager: ToolManager, message_builder: MessageBuilder) -> None:
        self.tool_manager = tool_manager
        self.message_builder = message_builder

    def _latest_user_message(self, messages: list[ChatMessage]) -> str:
        for message in reversed(messages):
            if message.get("role") == "user":
                return message.get("content", "")
        return ""

    def _planned_route_reason(self, planned_call: PlannedToolCall) -> str:
        return planned_call.route_reason or str(planned_call.arguments.get("route_reason") or "")

    def _emit_status(
        self,
        status_callback: StatusCallback | None,
        message: str,
        emitted_statuses: set[str] | None = None,
    ) -> None:
        if status_callback is None:
            return
        clean_message = str(message or "").strip()
        if not clean_message:
            return
        if emitted_statuses is not None:
            if clean_message in emitted_statuses:
                return
            emitted_statuses.add(clean_message)
        status_callback(clean_message)

    def prepare_messages(
            self,
            messages: list[ChatMessage],
            planned_call: PlannedToolCall,
        ) -> tuple[list[ChatMessage], ToolResult]:
            """Run the search workflow and return model messages ready for final synthesis."""

            model_messages, workflow_result, _performance = self.prepare(
                messages,
                planned_call,
            )
            return model_messages, workflow_result
    def prepare(
            self,
            messages: list[ChatMessage],
            planned_call: PlannedToolCall,
            status_callback: StatusCallback | None = None,
            emitted_statuses: set[str] | None = None,
        ) -> tuple[list[ChatMessage], ToolResult, SearchWorkflowPerformance]:
            """Prepare search context and collect performance metrics."""

            workflow_started_at = perf_counter()
            user_message = self._latest_user_message(messages)
            query = str(planned_call.arguments.get("query", user_message))
            search_kwargs = self._web_search_tool_arguments(planned_call.arguments, query=query)
            should_read_pages = self._should_read_web_pages(user_message or query)
            read_top_k = self._search_workflow_read_top_k(planned_call)
            logger.info("Search workflow started: query=%s", safe_log_field("query", query))
            route_reason = self._planned_route_reason(planned_call) or WEB_SEARCH_ROUTE_REASON
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
                if selected_items:
                    self._emit_status(status_callback, STATUS_WEB_READING, emitted_statuses)
                reader_started_at = perf_counter()
                try:
                    reader_pairs = self._read_search_pages_concurrently(selected_items)
                except Exception as exc:
                    reader_pairs = []
                    logger.warning(
                        "Search workflow web_reader batch failed; continuing with search results: error=%s",
                        exc,
                        exc_info=True,
                    )
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
                success_pages=successful_reader_count,
                failed_pages=max(selected_page_count - successful_reader_count, 0),
                cache_hit_count=cache_hit_count,
            )
            workflow_payload = {
                "query": query,
                "route_reason": route_reason,
                "search_success": search_result.success,
                "search_error": search_result.error,
                "search_results": compact_search_items,
                "read_pages": compact_pages,
                "web_pages_read": should_read_pages,
                "success_pages": successful_reader_count,
                "failed_pages": max(selected_page_count - successful_reader_count, 0),
                "cache_hit_count": cache_hit_count,
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
            model_messages = self.message_builder.with_search_workflow_result(messages, workflow_result)
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
    def stream_summary(
            self,
            messages: list[ChatMessage],
            performance: SearchWorkflowPerformance,
            llm_client,
            model: str | None = None,
        ) -> Iterator[str]:
            summarize_started_at = perf_counter()
            try:
                yield from llm_client.stream_complete_chat(messages, model=model)
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
    def _elapsed_ms(self, started_at: float) -> float:
            return round((perf_counter() - started_at) * 1000, 2)
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
    def _search_workflow_read_top_k(self, planned_call: PlannedToolCall) -> int:
            configured_default = self._positive_int(
                getattr(self.settings, "search_workflow_read_top_k", DEFAULT_SEARCH_WORKFLOW_READ_TOP_K),
                default=DEFAULT_SEARCH_WORKFLOW_READ_TOP_K,
            )
            requested_value = planned_call.arguments.get("read_top_k")
            resolved_value = self._positive_int(
                requested_value,
                default=configured_default,
            )
            return min(resolved_value, MAX_SEARCH_WORKFLOW_READ_TOP_K)
    def _compact_search_workflow_context(
            self,
            query: str,
            search_success: bool,
            search_error: str | None,
            search_items: list[Any],
            pages: list[dict[str, Any]],
            max_context_chars: int,
            web_pages_read: bool,
            success_pages: int = 0,
            failed_pages: int = 0,
            cache_hit_count: int = 0,
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
                success_pages=success_pages,
                failed_pages=failed_pages,
                cache_hit_count=cache_hit_count,
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
            success_pages: int = 0,
            failed_pages: int = 0,
            cache_hit_count: int = 0,
        ) -> int:
            payload = {
                "query": query,
                "search_success": search_success,
                "search_error": search_error,
                "search_results": search_items,
                "read_pages": pages,
                "web_pages_read": web_pages_read,
                "success_pages": success_pages,
                "failed_pages": failed_pages,
                "cache_hit_count": cache_hit_count,
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
    def _should_read_web_pages(self, message: str) -> bool:
            """Return True only for deeper questions where snippets are unlikely to be enough."""

            lowered = message.lower().strip()
            if not lowered:
                return False

            deep_analysis_keywords = (
                "分析",
                "对比",
                "比较",
                "总结",
                "详细分析",
                "详细解析",
                "详细",
                "为什么",
                "原理",
                "教程",
                "指南",
                "步骤",
                "怎么做",
                "如何",
                "解析",
                "深入",
                "深度",
                "analysis",
                "analyze",
                "compare",
                "comparison",
                "summarize",
                "summary",
                "detail",
                "detailed",
                "why",
                "principle",
                "how it works",
                "tutorial",
                "guide",
                "deep analysis",
                "in-depth",
                "in depth",
            )
            if any(keyword in lowered for keyword in deep_analysis_keywords):
                return True

            if re.search(r"https?://\S+|www\.\S+|\b[a-z0-9][a-z0-9.-]*\.[a-z]{2,}(?:/\S*)?", lowered) and any(
                keyword in lowered
                for keyword in (
                    "读",
                    "读取",
                    "打开",
                    "网页",
                    "文章",
                    "页面",
                    "read",
                    "open",
                    "page",
                    "article",
                )
            ):
                return True

            article_summary_keywords = (
                "总结这篇文章",
                "总结这篇",
                "总结文章",
                "summarize this article",
            )
            if any(keyword in lowered for keyword in article_summary_keywords):
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
