from __future__ import annotations

from typing import Any, Mapping

from pydantic import BaseModel, Field, model_validator


class PlanStep(BaseModel):
    """One executable or reasoning step in an agent plan."""

    step_id: str = Field(..., min_length=1, description="Stable id for this step.")
    description: str = Field(..., min_length=1, description="Human-readable task description.")
    tool_name: str | None = Field(default=None, description="Tool to call, or None for no-tool work.")
    tool_args: dict[str, Any] = Field(default_factory=dict, description="Arguments passed to the tool.")
    depends_on: list[str] = Field(default_factory=list, description="Step ids that must finish first.")


class AgentPlan(BaseModel):
    """Structured plan produced before the agent executes tools or answers."""

    question: str = Field(..., description="Original user question being planned.")
    steps: list[PlanStep] = Field(..., min_length=1, description="Ordered task steps.")

    @model_validator(mode="after")
    def validate_step_graph(self) -> "AgentPlan":
        """Keep the plan easy to execute by validating ids and dependencies."""

        seen: set[str] = set()
        for step in self.steps:
            missing_dependencies = [dependency for dependency in step.depends_on if dependency not in seen]
            if missing_dependencies:
                missing = ", ".join(sorted(missing_dependencies))
                raise ValueError(f"Unknown or unordered plan dependencies: {missing}")
            if step.step_id in seen:
                raise ValueError(f"Duplicate plan step_id: {step.step_id}")
            seen.add(step.step_id)
        return self


class Planner:
    """Create a structured task plan from a user question and optional tool route."""

    DIRECT_ANSWER_STEP_ID = "direct_answer"
    TOOL_STEP_ID = "tool_1"
    FINAL_ANSWER_STEP_ID = "final_answer"

    def __init__(self, max_steps: int = 8) -> None:
        self.max_steps = max(int(max_steps), 1)

    def plan(
        self,
        question: str,
        planned_tool_call: Any | None = None,
    ) -> AgentPlan:
        """Return a direct-answer plan or a tool-backed plan for the question."""

        clean_question = str(question or "").strip()
        tool_name = self._tool_name(planned_tool_call)
        if not tool_name:
            return self.direct_answer_plan(clean_question)

        tool_args = self._tool_args(planned_tool_call)
        return self.tool_plan(clean_question, tool_name=tool_name, tool_args=tool_args)

    def direct_answer_plan(self, question: str) -> AgentPlan:
        """Plan simple questions as a single no-tool direct answer step."""

        # Simple questions stay as one no-tool step so the main flow can answer directly.
        return self._checked_plan(
            question=question,
            steps=[
                PlanStep(
                    step_id=self.DIRECT_ANSWER_STEP_ID,
                    description="Answer the user directly without calling a tool.",
                    tool_name=None,
                    tool_args={},
                    depends_on=[],
                )
            ],
        )

    def tool_plan(
        self,
        question: str,
        tool_name: str,
        tool_args: Mapping[str, Any] | None = None,
    ) -> AgentPlan:
        """Plan a tool call followed by a no-tool final answer step."""

        clean_tool_name = str(tool_name or "").strip()
        if not clean_tool_name:
            return self.direct_answer_plan(question)

        # Tool-backed plans mirror runtime order: collect tool context, then answer.
        return self._checked_plan(
            question=question,
            steps=[
                PlanStep(
                    step_id=self.TOOL_STEP_ID,
                    description=f"Call the {clean_tool_name} tool with the planned arguments.",
                    tool_name=clean_tool_name,
                    tool_args=dict(tool_args or {}),
                    depends_on=[],
                ),
                PlanStep(
                    step_id=self.FINAL_ANSWER_STEP_ID,
                    description="Generate the final answer from the available context and tool result.",
                    tool_name=None,
                    tool_args={},
                    depends_on=[self.TOOL_STEP_ID],
                ),
            ],
        )

    def _checked_plan(self, *, question: str, steps: list[PlanStep]) -> AgentPlan:
        if len(steps) > self.max_steps:
            raise ValueError(
                f"Agent plan requires {len(steps)} steps but MAX_AGENT_STEPS is {self.max_steps}."
            )
        return AgentPlan(question=question, steps=steps)

    def _tool_name(self, planned_tool_call: Any | None) -> str | None:
        if planned_tool_call is None:
            return None
        return str(getattr(planned_tool_call, "name", "") or "").strip() or None

    def _tool_args(self, planned_tool_call: Any | None) -> dict[str, Any]:
        arguments = getattr(planned_tool_call, "arguments", None)
        if isinstance(arguments, Mapping):
            return dict(arguments)
        return {}
