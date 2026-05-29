from typing import Any

from app.agent.executor import AgentExecutor
from app.agent.planner import Planner
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
