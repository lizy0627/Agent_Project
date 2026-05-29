from time import perf_counter
from typing import Iterator

from app.core.logger import get_logger
from app.core.safe_logging import safe_log_field
from app.services.agent_planner import DEFAULT_WEB_SEARCH_MAX_RESULTS, PlannedToolCall
from app.services.agent_types import (
    ChatMessage,
    DEFAULT_SEARCH_WORKFLOW_READ_TOP_K,
    MAX_SEARCH_SUMMARY_RESULTS,
    MAX_SEARCH_WORKFLOW_READ_TOP_K,
    SearchWorkflowPerformance,
    StatusCallback,
    STATUS_WEB_READING,
)
from app.services.message_builder import MessageBuilder
from app.tools.base import ToolResult
from app.tools.registry import ToolRegistry
from app.workflow import create_research_workflow


logger = get_logger(__name__)


class SearchWorkflow:
    """Adapter that runs the research_workflow and builds Agent-ready context."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        message_builder: MessageBuilder,
        read_top_k: int = DEFAULT_SEARCH_WORKFLOW_READ_TOP_K,
    ) -> None:
        self.tool_registry = tool_registry
        self.message_builder = message_builder
        self.read_top_k = read_top_k

    def prepare_messages(
        self,
        messages: list[ChatMessage],
        planned_call: PlannedToolCall,
    ) -> tuple[list[ChatMessage], ToolResult]:
        model_messages, workflow_result, _performance = self.prepare(messages, planned_call)
        return model_messages, workflow_result

    def prepare(
        self,
        messages: list[ChatMessage],
        planned_call: PlannedToolCall,
        status_callback: StatusCallback | None = None,
        emitted_statuses: set[str] | None = None,
    ) -> tuple[list[ChatMessage], ToolResult, SearchWorkflowPerformance]:
        started_at = perf_counter()
        user_message = self._latest_user_message(messages)
        query = str(planned_call.arguments.get("query") or user_message).strip()
        max_results = self._max_results(planned_call)
        read_top_k = self._read_top_k(planned_call)

        logger.info("Research workflow started: query=%s", safe_log_field("query", query))
        if read_top_k > 0:
            self._emit_status(status_callback, STATUS_WEB_READING, emitted_statuses)

        workflow = create_research_workflow(
            self.tool_registry,
            max_results=max_results,
            read_top_k=read_top_k,
        )
        execution = workflow.run(
            {
                "query": query,
                "search_depth": planned_call.arguments.get("search_depth", "basic"),
            }
        )
        workflow_result = execution.to_tool_result()
        output = workflow_result.result if isinstance(workflow_result.result, dict) else {}
        workflow_result = self._with_route_reason(workflow_result, planned_call)
        model_messages = self.message_builder.with_search_workflow_result(messages, workflow_result)

        performance = SearchWorkflowPerformance(
            started_at=started_at,
            search_seconds=0.0,
            reader_seconds=0.0,
            success_pages=self._int_value(output.get("success_pages")),
            failed_pages=self._int_value(output.get("failed_pages")),
            cache_hit_count=0,
        )
        logger.info(
            "Research workflow finished: success=%s success_pages=%s failed_pages=%s duration_ms=%s",
            workflow_result.success,
            performance.success_pages,
            performance.failed_pages,
            workflow_result.duration_ms,
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
            logger.info("[ResearchWorkflow] streaming summarize done, cost=%.2fs", llm_seconds)
            self._log_search_workflow_performance(performance, llm_seconds=llm_seconds)

    def _log_search_workflow_performance(
        self,
        performance: SearchWorkflowPerformance,
        llm_seconds: float,
    ) -> None:
        logger.info(
            (
                "[ResearchWorkflow] total=%.2fs search=%.2fs reader=%.2fs llm=%.2fs "
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

    def _latest_user_message(self, messages: list[ChatMessage]) -> str:
        for message in reversed(messages):
            if message.get("role") == "user":
                return message.get("content", "")
        return ""

    def _max_results(self, planned_call: PlannedToolCall) -> int:
        requested = self._int_value(planned_call.arguments.get("max_results"), DEFAULT_WEB_SEARCH_MAX_RESULTS)
        return min(max(requested, 1), MAX_SEARCH_SUMMARY_RESULTS)

    def _read_top_k(self, planned_call: PlannedToolCall) -> int:
        requested = self._int_value(planned_call.arguments.get("read_top_k"), self.read_top_k)
        return min(max(requested, 0), MAX_SEARCH_WORKFLOW_READ_TOP_K)

    def _with_route_reason(self, workflow_result: ToolResult, planned_call: PlannedToolCall) -> ToolResult:
        route_reason = planned_call.route_reason or str(planned_call.arguments.get("route_reason") or "")
        if not route_reason or not isinstance(workflow_result.result, dict):
            return workflow_result

        result = dict(workflow_result.result)
        result.setdefault("route_reason", route_reason)
        return ToolResult(
            name=workflow_result.name,
            success=workflow_result.success,
            result=result,
            error=workflow_result.error,
            duration_ms=workflow_result.duration_ms,
            error_code=workflow_result.error_code,
            error_message=workflow_result.error_message,
            retryable=workflow_result.retryable,
        )

    def _emit_status(
        self,
        status_callback: StatusCallback | None,
        message: str,
        emitted_statuses: set[str] | None,
    ) -> None:
        if status_callback is None:
            return
        clean_message = message.strip()
        if not clean_message:
            return
        if emitted_statuses is not None:
            if clean_message in emitted_statuses:
                return
            emitted_statuses.add(clean_message)
        status_callback(clean_message)

    def _int_value(self, value, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _elapsed_seconds(self, started_at: float) -> float:
        return round(perf_counter() - started_at, 2)
