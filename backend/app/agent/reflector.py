from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from backend.app.agent.state import AgentTrace


class ReflectionResult(BaseModel):
    """Lightweight evaluation of an agent run."""

    status: str = Field(..., description="success, failed, or needs_attention.")
    summary: str = Field(..., description="Short operational summary of the run.")
    failed_steps: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Reflector:
    """Inspect an AgentTrace and produce a compact reflection for logs or UI."""

    def reflect(self, trace: AgentTrace) -> ReflectionResult:
        failed_steps = [
            step.step_id or step.step
            for step in trace.steps
            if step.status == "failed"
        ]
        skipped_steps = [
            step.step_id or step.step
            for step in trace.steps
            if step.status == "skipped"
        ]
        if failed_steps:
            status = "failed"
            summary = "Agent run completed with failed steps."
        elif skipped_steps:
            status = "needs_attention"
            summary = "Agent run completed with skipped steps."
        else:
            status = "success"
            summary = "Agent run completed successfully."

        return ReflectionResult(
            status=status,
            summary=summary,
            failed_steps=failed_steps,
            metadata={
                "trace_id": trace.trace_id,
                "step_count": len(trace.steps),
                "skipped_steps": skipped_steps,
                "duration_ms": trace.duration_ms,
            },
        )


__all__ = ["ReflectionResult", "Reflector"]
