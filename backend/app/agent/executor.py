from __future__ import annotations

from time import perf_counter
from typing import Any

from backend.app.agent.state import AgentStep, AgentTrace
from backend.app.agent.planner import AgentPlan, PlanStep
from backend.app.tools.base import ToolResult
from backend.app.tools.registry import TOOL_EXECUTION_ERROR, ToolRegistry


AgentTraceStep = AgentStep


class AgentExecutor:
    """Execute an AgentPlan step by step through ToolRegistry."""

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self.tool_registry = tool_registry

    def execute(self, plan: AgentPlan) -> AgentTrace:
        """Run every step in order and return a complete trace."""

        trace = AgentTrace(question=plan.question, plan=plan.model_dump())
        completed: dict[str, AgentStep] = {}
        for step in plan.steps:
            step_trace = self._execute_step(step, completed)
            trace.steps.append(step_trace)
            completed[step.step_id] = step_trace
        return trace

    def last_tool_result(self, trace: AgentTrace) -> ToolResult | None:
        """Return the last ToolResult-like observation from the executor trace."""

        for step in reversed(trace.steps):
            observation = step.observation
            if isinstance(observation, ToolResult):
                return observation
        return None

    def _execute_step(
        self,
        step: PlanStep,
        completed: dict[str, AgentStep],
    ) -> AgentStep:
        started_at = perf_counter()
        blocked_by = self._failed_dependencies(step, completed)
        if blocked_by:
            return self._trace_step(
                step,
                status="skipped",
                observation={"message": "Skipped because a dependency failed.", "failed_dependencies": blocked_by},
                duration_ms=self._elapsed_ms(started_at),
            )

        if not step.tool_name:
            # No-tool steps are still recorded so direct answers and final synthesis are visible.
            return self._trace_step(
                step,
                status="success",
                observation={"message": "No tool required for this step."},
                duration_ms=self._elapsed_ms(started_at),
            )

        try:
            tool_result = self.tool_registry.run_tool(step.tool_name, step.tool_args)
        except Exception as exc:
            return self._trace_step(
                step,
                status="failed",
                observation=None,
                error=str(exc),
                duration_ms=self._elapsed_ms(started_at),
            )

        return self._trace_step(
            step,
            status="success" if tool_result.success else "failed",
            observation=tool_result,
            error=tool_result.error_message or tool_result.error,
            duration_ms=tool_result.duration_ms if tool_result.duration_ms is not None else self._elapsed_ms(started_at),
        )

    def _failed_dependencies(
        self,
        step: PlanStep,
        completed: dict[str, AgentTraceStep],
    ) -> list[str]:
        failed_dependencies: list[str] = []
        for dependency in step.depends_on:
            dependency_trace = completed.get(dependency)
            if dependency_trace is None or dependency_trace.status == "failed":
                failed_dependencies.append(dependency)
        return failed_dependencies

    def _trace_step(
        self,
        step: PlanStep,
        status: str,
        observation: Any | None,
        duration_ms: float,
        error: str | None = None,
    ) -> AgentStep:
        return AgentStep(
            step="tool_call" if step.tool_name else "final_answer",
            step_id=step.step_id,
            description=step.description,
            tool_name=step.tool_name,
            tool_args=step.tool_args,
            depends_on=step.depends_on,
            status=status,
            observation=observation,
            error=error,
            duration_ms=duration_ms,
        )

    def _elapsed_ms(self, started_at: float) -> float:
        return round((perf_counter() - started_at) * 1000, 2)


def tool_result_to_observation(result: ToolResult | None) -> dict[str, Any] | None:
    """Serialize ToolResult for API traces without exposing Python objects."""

    if result is None:
        return None
    return {
        "name": result.name,
        "success": result.success,
        "result": result.result,
        "error": result.error,
        "duration_ms": result.duration_ms,
        "error_code": result.error_code or (None if result.success else TOOL_EXECUTION_ERROR),
        "error_message": result.error_message,
        "retryable": result.retryable,
    }
