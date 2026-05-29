from time import perf_counter
from typing import Any, Iterator

from backend.app.agent.executor import AgentExecutor, AgentTrace, tool_result_to_observation
from backend.app.agent.planner import AgentPlan, Planner
from backend.app.core.config import Settings
from backend.app.core.logger import get_logger
from backend.app.core.safe_logging import safe_log_data
from backend.app.mcp.manager import MCPManager
from backend.app.mcp.router import MCPRouter
from backend.app.agent.planner import AgentPlanner, PlannedToolCall
from backend.app.services.agent_types import (
    AgentReply,
    AgentTraceStep,
    ChatMessage,
    StatusCallback,
    STATUS_CALCULATING,
    STATUS_GENERATING,
    STATUS_GETTING_TIME,
    STATUS_MCP_CALLING,
    STATUS_MCP_CONNECTING,
    STATUS_SUMMARIZING,
    STATUS_WEB_SEARCHING,
)
from backend.app.services.llm_client import LLMClient
from backend.app.services.message_builder import MessageBuilder
from backend.app.services.search_workflow import SearchWorkflow
from backend.app.tools import create_default_tool_manager
from backend.app.tools.base import ToolResult
from backend.app.tools.mcp_tool import MCPTool
from backend.app.tools.tool_manager import ToolManager


logger = get_logger(__name__)


class AgentService:
    """Coordinate planning, tools, search workflow, message building, and LLM calls."""

    def __init__(self, settings: Settings, tool_manager: ToolManager | None = None) -> None:
        self.settings = settings
        self.llm_client = LLMClient(settings)
        self.model = self.llm_client.model
        self.mcp_manager = MCPManager(
            timeout_seconds=settings.mcp_timeout_seconds,
            modelscope_url=settings.modelscope_mcp_url,
        )
        self.tool_manager = tool_manager or create_default_tool_manager(
            tavily_api_key=settings.tavily_api_key,
            web_search_provider=settings.web_search_provider,
            web_search_timeout_seconds=settings.web_search_timeout_seconds,
            web_reader_timeout_seconds=settings.web_reader_timeout_seconds,
            mcp_enabled=settings.mcp_enabled,
            mcp_manager=self.mcp_manager,
        )
        self._inject_mcp_manager_into_tool()
        self.mcp_router = MCPRouter(self.mcp_manager)
        self.tool_route_planner = AgentPlanner(settings=self.settings, mcp_router=self.mcp_router)
        self.planner = Planner(max_steps=settings.max_agent_steps)
        self.executor = AgentExecutor(self.tool_manager)
        self.message_builder = MessageBuilder()
        self.search_workflow = SearchWorkflow(
            self.tool_manager,
            self.message_builder,
            read_top_k=settings.search_workflow_read_top_k,
        )

    def _inject_mcp_manager_into_tool(self) -> None:
        mcp_tool = self.tool_manager.get_tool("mcp_tool")
        if isinstance(mcp_tool, MCPTool) and mcp_tool.manager is None:
            mcp_tool.manager = self.mcp_manager

    def chat(self, messages: list[ChatMessage], model: str | None = None) -> AgentReply:
        """Send a chat request with complete context and return model text."""

        started_at = perf_counter()
        status = "failed"
        trace: list[AgentTraceStep] = []
        try:
            planned_call, agent_plan = self._trace_plan_tool_call(messages, trace)
            if planned_call and planned_call.name == "web_search":
                reply = self._handle_search_workflow(messages, planned_call, model=model, trace=trace)
                status = "success"
                return reply

            executor_trace = self.executor.execute(agent_plan)
            tool_result = self.executor.last_tool_result(executor_trace)
            self._append_executor_trace(trace, executor_trace)
            model_messages = self.message_builder.with_tool_result(messages, tool_result)
            reply = self._complete_chat_with_trace(model_messages, trace, model=model)
            status = "success"
            return AgentReply(content=reply, tool_result=tool_result, trace=trace)
        except Exception:
            logger.exception(
                "Agent execution failed: model=%s duration_ms=%.2f",
                model or self.model,
                self._elapsed_ms(started_at),
            )
            raise
        finally:
            logger.info(
                "Agent execution finished: model=%s status=%s duration_ms=%.2f",
                model or self.model,
                status,
                self._elapsed_ms(started_at),
            )

    def stream_chat(self, messages: list[ChatMessage], model: str | None = None) -> Iterator[str]:
        """Stream a chat request with complete context."""

        stream, _tool_result, _trace = self.stream_chat_with_tool_result(messages, model=model)
        yield from stream

    def stream_chat_with_tool_result(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        status_callback: StatusCallback | None = None,
    ) -> tuple[Iterator[str], ToolResult | None, list[AgentTraceStep]]:
        """Return a streaming iterator and the tool metadata used to build it."""

        trace: list[AgentTraceStep] = []
        emitted_statuses: set[str] = set()
        started_at = perf_counter()
        initial_tool_name = self._emit_initial_tool_status(messages, status_callback, emitted_statuses)
        try:
            planned_call, agent_plan = self._trace_plan_tool_call(messages, trace)
            if planned_call and planned_call.name == "web_search":
                if initial_tool_name != "web_search":
                    self._emit_status(status_callback, STATUS_WEB_SEARCHING, emitted_statuses)
                model_messages, workflow_result, performance = self.search_workflow.prepare(
                    messages,
                    planned_call,
                    status_callback=status_callback,
                    emitted_statuses=emitted_statuses,
                )
                self._append_tool_trace(trace, planned_call, workflow_result)
                self._emit_status(status_callback, STATUS_GENERATING, emitted_statuses)
                logger.info("[SearchWorkflow] streaming summarize start")
                stream = self.search_workflow.stream_summary(
                    model_messages,
                    performance,
                    self.llm_client,
                    model=model,
                )
                logger.info(
                    "Agent stream prepared: model=%s duration_ms=%.2f",
                    model or self.model,
                    self._elapsed_ms(started_at),
                )
                return stream, workflow_result, trace

            self._emit_planned_tool_status(
                planned_call,
                status_callback,
                emitted_statuses,
                initial_tool_name=initial_tool_name,
            )
            executor_trace = self.executor.execute(agent_plan)
            tool_result = self.executor.last_tool_result(executor_trace)
            self._append_executor_trace(trace, executor_trace)
            if tool_result is not None:
                self._emit_status(status_callback, STATUS_GENERATING, emitted_statuses)
            model_messages = self.message_builder.with_tool_result(messages, tool_result)
            stream = self.llm_client.stream_complete_chat(model_messages, model=model)
            logger.info(
                "Agent stream prepared: model=%s duration_ms=%.2f",
                model or self.model,
                self._elapsed_ms(started_at),
            )
            return stream, tool_result, trace
        except Exception:
            logger.exception(
                "Agent stream preparation failed: model=%s duration_ms=%.2f",
                model or self.model,
                self._elapsed_ms(started_at),
            )
            raise

    def prepare_chat_messages(
        self,
        messages: list[ChatMessage],
    ) -> tuple[list[ChatMessage], ToolResult | None]:
        """Apply optional local tool context before calling the model."""

        planned_call = self._plan_tool_call(messages)
        agent_plan = self._plan_agent_steps(messages, planned_call)
        executor_trace = self.executor.execute(agent_plan)
        tool_result = self.executor.last_tool_result(executor_trace)
        return self.message_builder.with_tool_result(messages, tool_result), tool_result

    def _handle_search_workflow(
        self,
        messages: list[ChatMessage],
        planned_call: PlannedToolCall,
        model: str | None = None,
        trace: list[AgentTraceStep] | None = None,
    ) -> AgentReply:
        """Run search, read top pages, and ask the model to synthesize an answer."""

        active_trace = trace if trace is not None else []
        model_messages, workflow_result, performance = self.search_workflow.prepare(messages, planned_call)
        self._append_tool_trace(active_trace, planned_call, workflow_result)
        logger.info("[SearchWorkflow] llm summarize start")
        summarize_started_at = perf_counter()
        try:
            reply = self.llm_client.complete_chat(model_messages, model=model)
            self._append_model_trace(active_trace, summarize_started_at, "success")
        except Exception as exc:
            self._append_model_trace(active_trace, summarize_started_at, "failed", message=str(exc))
            raise
        finally:
            logger.info(
                "[SearchWorkflow] llm summarize done, cost=%.2fs",
                self._elapsed_seconds(summarize_started_at),
            )
        self.search_workflow._log_search_workflow_performance(
            performance,
            llm_seconds=self._elapsed_seconds(summarize_started_at),
        )
        return AgentReply(content=reply, tool_result=workflow_result, trace=active_trace)

    def _complete_chat_with_trace(
        self,
        messages: list[ChatMessage],
        trace: list[AgentTraceStep],
        model: str | None = None,
    ) -> str:
        """Call the model and append a final_answer trace step."""

        started_at = perf_counter()
        try:
            reply = self.llm_client.complete_chat(messages, model=model)
        except Exception as exc:
            self._append_model_trace(trace, started_at, "failed", message=str(exc))
            raise

        self._append_model_trace(trace, started_at, "success")
        return reply

    def _trace_plan_tool_call(
        self,
        messages: list[ChatMessage],
        trace: list[AgentTraceStep],
    ) -> tuple[PlannedToolCall | None, AgentPlan]:
        """Plan the optional tool call and append a front-end friendly trace step."""

        started_at = perf_counter()
        try:
            planned_call = self._plan_tool_call(messages)
            agent_plan = self._plan_agent_steps(messages, planned_call)
        except Exception as exc:
            trace.append(
                AgentTraceStep(
                    step="planner",
                    status="failed",
                    message=str(exc),
                    duration_ms=self._elapsed_ms(started_at),
                )
            )
            raise

        metadata = self._plan_trace_metadata(agent_plan, planned_call)
        logger.info("Planner output: %s", safe_log_data(metadata))
        if planned_call is None:
            trace.append(
                AgentTraceStep(
                    step="planner",
                    status="success",
                    message="Planned direct answer.",
                    duration_ms=self._elapsed_ms(started_at),
                    metadata=metadata,
                )
            )
            return None, agent_plan

        trace.append(
            AgentTraceStep(
                step="planner",
                status="success",
                message=f"Selected tool: {planned_call.name}.",
                tool_name=planned_call.name,
                duration_ms=self._elapsed_ms(started_at),
                metadata=metadata or None,
            )
        )
        return planned_call, agent_plan

    def _append_tool_trace(
        self,
        trace: list[AgentTraceStep],
        planned_call: PlannedToolCall | None,
        tool_result: ToolResult | None,
    ) -> None:
        """Append a tool_call trace step when a local tool was executed."""

        if planned_call is None and tool_result is None:
            return

        tool_name = tool_result.name if tool_result is not None else planned_call.name if planned_call else None
        status = "success" if tool_result is not None and tool_result.success else "failed"
        message = None
        if tool_result is None:
            status = "skipped"
            message = "Tool was planned but not executed"
        elif not tool_result.success:
            message = tool_result.error_message or tool_result.error

        trace.append(
            AgentTraceStep(
                step="tool_call",
                status=status,
                message=message or f"Tool call finished: {tool_name}",
                tool_name=tool_name,
                duration_ms=tool_result.duration_ms if tool_result is not None else None,
                metadata={
                    "tool_args": dict(getattr(planned_call, "arguments", {}) or {}),
                }
                if planned_call is not None
                else None,
            )
        )
        trace.append(
            AgentTraceStep(
                step="observation",
                status=status,
                message=message or "Observed tool result.",
                tool_name=tool_name,
                observation=tool_result_to_observation(tool_result),
                duration_ms=tool_result.duration_ms if tool_result is not None else None,
            )
        )

    def _append_executor_trace(self, trace: list[AgentTraceStep], executor_trace: AgentTrace) -> None:
        """Expose every executor observation through the API trace field."""

        for step in executor_trace.steps:
            metadata: dict[str, Any] = {
                "step_id": step.step_id,
                "description": step.description,
                "tool_args": step.tool_args,
                "depends_on": step.depends_on,
            }
            if step.tool_name:
                trace.append(
                    AgentTraceStep(
                        step="tool_call",
                        status=step.status,
                        message=step.error or f"Tool call finished: {step.tool_name}",
                        tool_name=step.tool_name,
                        duration_ms=step.duration_ms,
                        metadata=metadata,
                    )
                )
                trace.append(
                    AgentTraceStep(
                        step="observation",
                        status=step.status,
                        message=step.error or "Observed tool result.",
                        tool_name=step.tool_name,
                        observation=self._serialize_observation(step.observation),
                        duration_ms=step.duration_ms,
                        metadata=metadata,
                    )
                )
                continue

            trace.append(
                AgentTraceStep(
                    step="observation",
                    status=step.status,
                    message=step.error or step.description,
                    observation=self._serialize_observation(step.observation),
                    duration_ms=step.duration_ms,
                    metadata=metadata,
                )
            )

    def _append_model_trace(
        self,
        trace: list[AgentTraceStep],
        started_at: float,
        status: str,
        message: str | None = None,
    ) -> None:
        """Append the final model generation step."""

        trace.append(
            AgentTraceStep(
                step="final_answer",
                status=status,
                message=message,
                duration_ms=self._elapsed_ms(started_at),
            )
        )

    def _emit_initial_tool_status(
        self,
        messages: list[ChatMessage],
        status_callback: StatusCallback | None,
        emitted_statuses: set[str],
    ) -> str | None:
        """Emit an early status for likely local tool work before any slow discovery."""

        tool_name = self._likely_tool_name_for_status(messages)
        if tool_name is None:
            return None

        if tool_name == "mcp_tool":
            self._emit_status(status_callback, STATUS_MCP_CONNECTING, emitted_statuses)
            return tool_name

        message = self._status_message_for_tool(tool_name)
        if message:
            self._emit_status(status_callback, message, emitted_statuses)
        return tool_name

    def _emit_planned_tool_status(
        self,
        planned_call: PlannedToolCall | None,
        status_callback: StatusCallback | None,
        emitted_statuses: set[str],
        initial_tool_name: str | None = None,
    ) -> None:
        if planned_call is None:
            return

        if planned_call.name == "mcp_tool":
            if initial_tool_name != "mcp_tool":
                self._emit_status(status_callback, STATUS_MCP_CONNECTING, emitted_statuses)
            self._emit_status(status_callback, STATUS_MCP_CALLING, emitted_statuses)
            return

        if initial_tool_name == planned_call.name:
            return

        message = self._status_message_for_tool(planned_call.name)
        if message:
            self._emit_status(status_callback, message, emitted_statuses)

    def _likely_tool_name_for_status(self, messages: list[ChatMessage]) -> str | None:
        user_message = self._latest_user_message(messages)
        if not user_message:
            return None
        return self.tool_route_planner.likely_tool_name_for_status(user_message)

    def _status_message_for_tool(self, tool_name: str) -> str | None:
        return {
            "web_search": STATUS_WEB_SEARCHING,
            "calculate": STATUS_CALCULATING,
            "summarize_text": STATUS_SUMMARIZING,
            "get_current_time": STATUS_GETTING_TIME,
        }.get(tool_name)

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

    def _plan_tool_call(self, messages: list[ChatMessage]) -> PlannedToolCall | None:
        return self.tool_route_planner.plan(messages)

    def _plan_agent_steps(
        self,
        messages: list[ChatMessage],
        planned_call: PlannedToolCall | None,
    ) -> AgentPlan:
        """Build the structured Pydantic plan used by traces and debugging."""

        return self.planner.plan(self._latest_user_message(messages), planned_call)

    def _latest_user_message(self, messages: list[ChatMessage]) -> str:
        return self.tool_route_planner.latest_user_message(messages)

    def _plan_trace_metadata(
        self,
        agent_plan: AgentPlan,
        planned_call: PlannedToolCall | None,
    ) -> dict[str, Any]:
        """Attach the structured plan without changing the legacy trace shape."""

        metadata: dict[str, Any] = {"plan": agent_plan.model_dump()}
        if planned_call is None:
            return metadata
        if planned_call.route_score:
            metadata["route_score"] = planned_call.route_score
        if planned_call.route_reason:
            metadata["route_reason"] = planned_call.route_reason
        return metadata

    def _serialize_observation(self, observation: Any) -> Any:
        if isinstance(observation, ToolResult):
            return tool_result_to_observation(observation)
        return observation

    def _elapsed_seconds(self, started_at: float) -> float:
        return round(perf_counter() - started_at, 2)

    def _elapsed_ms(self, started_at: float) -> float:
        return round((perf_counter() - started_at) * 1000, 2)

    def _safe_planned_tool_log(self, planned_call: PlannedToolCall | None) -> dict | None:
        if planned_call is None:
            return None
        return {
            "name": planned_call.name,
            "arguments": safe_log_data(planned_call.arguments),
            "route_score": planned_call.route_score,
            "route_reason": planned_call.route_reason,
        }
