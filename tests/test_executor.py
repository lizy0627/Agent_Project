from typing import Any

from app.agent.executor import AgentExecutor
from app.agent.planner import AgentPlan, Planner, PlanStep
from app.tools.base import BaseTool
from app.tools.registry import ToolRegistry


class EchoTool(BaseTool):
    name = "echo"
    description = "Echo text."
    args_schema = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    def run(self, text: str) -> dict[str, str]:
        return {"text": text}


class RecordingTool(BaseTool):
    description = "Record call order."
    args_schema = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    def __init__(self, name: str, calls: list[tuple[str, str]]) -> None:
        self.name = name
        self.calls = calls

    def run(self, text: str) -> dict[str, str]:
        self.calls.append((self.name, text))
        return {"text": text}


class ExplodingRegistry(ToolRegistry):
    def run_tool(self, name: str, args: dict[str, Any] | None = None, max_retries: int = 1):
        raise RuntimeError("registry exploded")


def test_executor_runs_tool_step_and_records_observation():
    registry = ToolRegistry()
    registry.register(EchoTool())
    plan = Planner().tool_plan("echo hello", tool_name="echo", tool_args={"text": "hello"})

    trace = AgentExecutor(registry).execute(plan)

    assert [step.step_id for step in trace.steps] == ["tool_1", "final_answer"]
    assert trace.steps[0].status == "success"
    assert trace.steps[0].observation.success is True
    assert trace.steps[0].observation.result == {"text": "hello"}
    assert trace.steps[1].status == "success"


def test_executor_records_tool_registry_exception_without_crashing():
    plan = Planner().tool_plan("echo hello", tool_name="echo", tool_args={"text": "hello"})

    trace = AgentExecutor(ExplodingRegistry()).execute(plan)

    assert trace.steps[0].status == "failed"
    assert trace.steps[0].error == "registry exploded"
    assert trace.steps[1].status == "skipped"
    assert trace.steps[1].observation["failed_dependencies"] == ["tool_1"]


def test_executor_runs_multiple_tool_steps_in_order():
    calls: list[tuple[str, str]] = []
    registry = ToolRegistry()
    registry.register(RecordingTool("first_tool", calls))
    registry.register(RecordingTool("second_tool", calls))
    plan = AgentPlan(
        question="run two tools",
        steps=[
            PlanStep(
                step_id="tool_1",
                description="Run first tool.",
                tool_name="first_tool",
                tool_args={"text": "one"},
                depends_on=[],
            ),
            PlanStep(
                step_id="tool_2",
                description="Run second tool.",
                tool_name="second_tool",
                tool_args={"text": "two"},
                depends_on=["tool_1"],
            ),
            PlanStep(
                step_id="final_answer",
                description="Answer from both tools.",
                tool_name=None,
                tool_args={},
                depends_on=["tool_2"],
            ),
        ],
    )

    trace = AgentExecutor(registry).execute(plan)

    assert calls == [("first_tool", "one"), ("second_tool", "two")]
    assert [step.status for step in trace.steps] == ["success", "success", "success"]


def test_executor_skips_transitive_dependents_after_failed_tool():
    plan = AgentPlan(
        question="run a failing chain",
        steps=[
            PlanStep(
                step_id="tool_1",
                description="Call missing tool.",
                tool_name="missing_tool",
                tool_args={},
                depends_on=[],
            ),
            PlanStep(
                step_id="tool_2",
                description="Depends on failed tool.",
                tool_name="missing_tool",
                tool_args={},
                depends_on=["tool_1"],
            ),
            PlanStep(
                step_id="tool_3",
                description="Depends on skipped tool.",
                tool_name="missing_tool",
                tool_args={},
                depends_on=["tool_2"],
            ),
        ],
    )

    trace = AgentExecutor(ToolRegistry()).execute(plan)

    assert [step.status for step in trace.steps] == ["failed", "skipped", "skipped"]
    assert trace.steps[1].observation["failed_dependencies"] == ["tool_1"]
    assert trace.steps[2].observation["failed_dependencies"] == ["tool_2"]
