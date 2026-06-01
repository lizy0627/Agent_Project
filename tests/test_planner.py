import json
from typing import Any

import pytest

from app.agent.planner import LLMPlanGenerationError, LLMPlanGenerator, Planner
from app.tools.base import BaseTool
from app.tools.registry import ToolRegistry


class FakeLLMClient:
    def __init__(self, reply: Any) -> None:
        self.reply = reply
        self.calls = 0

    def complete_chat(self, messages, model=None):
        self.calls += 1
        if isinstance(self.reply, str):
            return self.reply
        return json.dumps(self.reply)


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


def test_planner_creates_single_direct_answer_step():
    plan = Planner().plan("hello")

    assert plan.question == "hello"
    assert len(plan.steps) == 1
    assert plan.steps[0].step_id == "direct_answer"
    assert plan.steps[0].tool_name is None
    assert plan.steps[0].tool_args == {}
    assert plan.steps[0].depends_on == []


def test_planner_creates_tool_step_and_final_answer_step():
    plan = Planner().tool_plan("calculate 1+1", tool_name="calculate", tool_args={"expression": "1+1"})

    assert [step.step_id for step in plan.steps] == ["tool_1", "final_answer"]
    assert plan.steps[0].tool_name == "calculate"
    assert plan.steps[0].tool_args == {"expression": "1+1"}
    assert plan.steps[1].tool_name is None
    assert plan.steps[1].depends_on == ["tool_1"]


def test_llm_plan_generator_accepts_valid_registered_tool_plan():
    registry = ToolRegistry()
    registry.register(EchoTool())
    llm = FakeLLMClient(
        {
            "question": "echo hello",
            "steps": [
                {
                    "step_id": "tool_1",
                    "description": "Echo the requested text.",
                    "tool_name": "echo",
                    "tool_args": {"text": "hello"},
                    "depends_on": [],
                },
                {
                    "step_id": "final_answer",
                    "description": "Answer from the echo result.",
                    "tool_name": None,
                    "tool_args": {},
                    "depends_on": ["tool_1"],
                },
            ],
        }
    )

    plan = LLMPlanGenerator(llm, registry).generate([{"role": "user", "content": "echo hello"}])

    assert [step.step_id for step in plan.steps] == ["tool_1", "final_answer"]
    assert plan.steps[0].tool_name == "echo"
    assert plan.steps[0].tool_args == {"text": "hello"}


def test_llm_plan_generator_skips_llm_for_obvious_direct_answer():
    registry = ToolRegistry()
    llm = FakeLLMClient({"unexpected": "planner should not be called"})

    plan = LLMPlanGenerator(llm, registry).generate([{"role": "user", "content": "你好"}])

    assert llm.calls == 0
    assert [step.step_id for step in plan.steps] == ["direct_answer"]
    assert plan.steps[0].tool_name is None


def test_llm_plan_generator_accepts_direct_answer_plan_from_llm():
    registry = ToolRegistry()
    llm = FakeLLMClient(
        {
            "question": "Explain recursion.",
            "steps": [
                {
                    "step_id": "direct_answer",
                    "description": "Answer directly without a tool.",
                    "tool_name": None,
                    "tool_args": {},
                    "depends_on": [],
                }
            ],
        }
    )

    plan = LLMPlanGenerator(llm, registry).generate([{"role": "user", "content": "Explain recursion."}])

    assert llm.calls == 1
    assert plan.steps[0].step_id == "direct_answer"
    assert plan.steps[0].tool_name is None


def test_llm_plan_generator_parses_json_with_markdown_and_trailing_commas():
    registry = ToolRegistry()
    registry.register(EchoTool())
    llm = FakeLLMClient(
        """
        Sure, here is the plan:
        ```json
        {
          "question": "echo hello",
          "steps": [
            {
              "step_id": "tool_1",
              "description": "Echo the requested text.",
              "tool_name": "echo",
              "tool_args": {"text": "hello"},
              "depends_on": [],
            },
            {
              "step_id": "final_answer",
              "description": "Answer from the echo result.",
              "tool_name": null,
              "tool_args": {},
              "depends_on": ["tool_1"],
            },
          ],
        }
        ```
        """
    )

    plan = LLMPlanGenerator(llm, registry).generate([{"role": "user", "content": "echo hello"}])

    assert [step.step_id for step in plan.steps] == ["tool_1", "final_answer"]
    assert plan.steps[0].tool_args == {"text": "hello"}


def test_llm_plan_generator_prefers_plan_object_when_extra_json_appears_first():
    registry = ToolRegistry()
    registry.register(EchoTool())
    llm = FakeLLMClient(
        """
        {"note": "not the plan"}
        {
          "question": "echo hello",
          "steps": [
            {
              "step_id": "tool_1",
              "description": "Echo the requested text.",
              "tool_name": "echo",
              "tool_args": {"text": "hello"},
              "depends_on": []
            }
          ]
        }
        """
    )

    plan = LLMPlanGenerator(llm, registry).generate([{"role": "user", "content": "echo hello"}])

    assert plan.question == "echo hello"
    assert plan.steps[0].tool_name == "echo"


def test_llm_plan_generator_rejects_unregistered_tool_name():
    registry = ToolRegistry()
    registry.register(EchoTool())
    llm = FakeLLMClient(
        {
            "question": "do something",
            "steps": [
                {
                    "step_id": "tool_1",
                    "description": "Call a tool that does not exist.",
                    "tool_name": "missing_tool",
                    "tool_args": {},
                    "depends_on": [],
                }
            ],
        }
    )

    with pytest.raises(LLMPlanGenerationError):
        LLMPlanGenerator(llm, registry).generate([{"role": "user", "content": "do something"}])
