from __future__ import annotations

from enum import Enum
from time import perf_counter
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class AgentState(str, Enum):
    """Overall lifecycle state for one agent request."""

    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class ToolCallRecord(BaseModel):
    """Structured record for one tool call."""

    tool_name: str = Field(..., description="Tool name selected by the planner.")
    tool_args: dict[str, Any] = Field(default_factory=dict, description="Arguments passed to the tool.")
    status: str = Field(default="running", description="running, success, failed, or skipped.")
    result: Any | None = Field(default=None, description="Tool result payload when available.")
    error: str | None = Field(default=None, description="Tool error when execution failed.")
    duration_ms: float | None = Field(default=None, description="Tool execution duration in milliseconds.")
    error_code: str | None = Field(default=None, description="Stable tool error code when available.")
    retryable: bool | None = Field(default=None, description="Whether the tool failure can be retried.")


class AgentStep(BaseModel):
    """One traceable step in an agent request lifecycle."""

    step: str = Field(..., description="Stable lifecycle key, for example planner/tool_call/observation/final_answer.")
    status: str = Field(default="running", description="running, success, failed, or skipped.")
    message: str | None = Field(default=None, description="Human-readable step summary.")
    step_id: str | None = Field(default=None, description="Planner step id when this comes from a plan.")
    description: str | None = Field(default=None, description="Planner step description.")
    tool_name: str | None = Field(default=None, description="Tool name when this step touches a tool.")
    tool_args: dict[str, Any] = Field(default_factory=dict, description="Tool arguments used by this step.")
    tool_call: ToolCallRecord | None = Field(default=None, description="Structured tool call record.")
    depends_on: list[str] = Field(default_factory=list, description="Planner step ids this step depends on.")
    observation: Any | None = Field(default=None, description="Tool output or execution observation.")
    error: str | None = Field(default=None, description="Error captured without crashing the agent.")
    duration_ms: float | None = Field(default=None, description="Step execution duration in milliseconds.")
    metadata: dict[str, Any] | None = Field(default=None, description="Optional structured UI/debug metadata.")

    def to_api_dict(self) -> dict[str, Any]:
        """Return a compact JSON-friendly dict for API and SSE trace payloads."""

        payload: dict[str, Any] = {
            "step": self.step,
            "status": self.status,
        }
        optional_values = {
            "message": self.message or self.error,
            "step_id": self.step_id,
            "description": self.description,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args or None,
            "tool_call": self.tool_call.model_dump(exclude_none=True) if self.tool_call else None,
            "depends_on": self.depends_on or None,
            "observation": self.observation,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }
        for key, value in optional_values.items():
            if value is not None:
                payload[key] = value
        return payload

    def to_dict(self) -> dict[str, Any]:
        """Compatibility alias used by the existing FastAPI serialization layer."""

        return self.to_api_dict()


class AgentTrace(BaseModel):
    """Complete execution trace for one agent request."""

    trace_id: str = Field(default_factory=lambda: str(uuid4()), description="Unique trace id.")
    state: AgentState = Field(default=AgentState.RUNNING, description="Overall trace state.")
    question: str | None = Field(default=None, description="Original user question.")
    plan: Any | None = Field(default=None, description="Structured planner output when available.")
    steps: list[AgentStep] = Field(default_factory=list, description="Ordered execution steps.")
    started_at: float = Field(default_factory=perf_counter, exclude=True)
    duration_ms: float | None = Field(default=None, description="Total trace duration in milliseconds.")

    @property
    def succeeded(self) -> bool:
        return all(step.status != "failed" for step in self.steps)

    def add_step(self, step: AgentStep) -> AgentStep:
        self.steps.append(step)
        if step.status == "failed":
            self.state = AgentState.FAILED
        elif self.state == AgentState.IDLE:
            self.state = AgentState.RUNNING
        return step

    def add_planner(
        self,
        *,
        status: str,
        message: str,
        duration_ms: float | None = None,
        metadata: dict[str, Any] | None = None,
        tool_name: str | None = None,
    ) -> AgentStep:
        return self.add_step(
            AgentStep(
                step="planner",
                status=status,
                message=message,
                duration_ms=duration_ms,
                metadata=metadata,
                tool_name=tool_name,
            )
        )

    def add_tool_call(
        self,
        *,
        tool_name: str,
        tool_args: dict[str, Any] | None = None,
        status: str = "running",
        message: str | None = None,
        duration_ms: float | None = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentStep:
        return self.add_step(
            AgentStep(
                step="tool_call",
                status=status,
                message=message or f"Call tool: {tool_name}",
                tool_name=tool_name,
                tool_args=dict(tool_args or {}),
                tool_call=ToolCallRecord(
                    tool_name=tool_name,
                    tool_args=dict(tool_args or {}),
                    status=status,
                    error=error,
                    duration_ms=duration_ms,
                ),
                duration_ms=duration_ms,
                error=error,
                metadata=metadata,
            )
        )

    def add_observation(
        self,
        *,
        status: str,
        observation: Any | None,
        message: str | None = None,
        tool_name: str | None = None,
        duration_ms: float | None = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentStep:
        return self.add_step(
            AgentStep(
                step="observation",
                status=status,
                message=message,
                tool_name=tool_name,
                observation=observation,
                duration_ms=duration_ms,
                error=error,
                metadata=metadata,
            )
        )

    def add_final_answer(
        self,
        *,
        status: str,
        message: str | None = None,
        duration_ms: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentStep:
        return self.add_step(
            AgentStep(
                step="final_answer",
                status=status,
                message=message,
                duration_ms=duration_ms,
                metadata=metadata,
            )
        )

    def finish(self, state: AgentState | str | None = None) -> None:
        if state is not None:
            self.state = AgentState(state)
        elif self.state != AgentState.FAILED:
            self.state = AgentState.SUCCESS if self.succeeded else AgentState.FAILED
        self.duration_ms = round((perf_counter() - self.started_at) * 1000, 2)

    def to_api_steps(self) -> list[dict[str, Any]]:
        return [step.to_api_dict() for step in self.steps]
