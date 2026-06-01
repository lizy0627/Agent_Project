from app.agent.reactor import ReActAgent, parse_action
from app.tools.base import BaseTool
from app.tools.registry import TOOL_NOT_FOUND, ToolRegistry
from backend.app.agent.reactor import ReActAgent as BackendReActAgent


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


class FailingTool(BaseTool):
    name = "fail"
    description = "Always fail."
    args_schema = {"type": "object", "properties": {}}

    def __init__(self) -> None:
        self.calls = 0

    def run(self) -> dict[str, object]:
        self.calls += 1
        return {"success": False, "error": "boom"}


class LargeTool(BaseTool):
    name = "large"
    description = "Return a large payload."
    args_schema = {"type": "object", "properties": {}}

    def run(self) -> dict[str, str]:
        return {"text": "x" * 10000}


class FakeLLM:
    def __init__(self, replies: list[str]) -> None:
        self.replies = replies
        self.calls: list[list[dict[str, str]]] = []

    def complete_chat(self, messages: list[dict[str, str]], model: str | None = None) -> str:
        self.calls.append(messages)
        return self.replies.pop(0)


def test_parse_action_accepts_json_tool_payload():
    tool_name, args = parse_action('{"tool": "echo", "args": {"text": "hello"}}')

    assert tool_name == "echo"
    assert args == {"text": "hello"}


def test_react_agent_runs_tool_and_appends_observation():
    registry = ToolRegistry()
    registry.register(EchoTool())
    llm = FakeLLM(
        [
            'Thought: I should echo it.\nAction: {"tool": "echo", "args": {"text": "hello"}}',
            "Thought: I have the observation.\nFinal Answer: hello",
        ]
    )

    result = ReActAgent(llm, registry).run("say hello")

    assert result.final_answer == "hello"
    assert [step.type for step in result.reasoning_steps] == [
        "thought",
        "action",
        "observation",
        "thought",
        "final_answer",
    ]
    assert result.reasoning_steps[2].observation["result"] == {"text": "hello"}
    assert result.tool_calls[0].tool_name == "echo"
    assert result.tool_calls[0].status == "success"


def test_react_agent_callback_receives_reasoning_steps_as_they_are_produced():
    registry = ToolRegistry()
    registry.register(EchoTool())
    llm = FakeLLM(
        [
            'Thought: I should echo it.\nAction: {"tool": "echo", "args": {"text": "hello"}}',
            "Thought: I have the observation.\nFinal Answer: hello",
        ]
    )
    events = []

    result = ReActAgent(llm, registry).run("say hello", callback=events.append)

    assert result.final_answer == "hello"
    assert [event.type for event in events] == [
        "thought",
        "action",
        "observation",
        "thought",
        "final_answer",
    ]
    assert events[1].tool_name == "echo"
    assert events[2].observation["result"] == {"text": "hello"}


def test_react_agent_accepts_structured_json_turns_and_writes_trace():
    registry = ToolRegistry()
    registry.register(EchoTool())
    llm = FakeLLM(
        [
            '{"thought":"Echo the text.","action":"echo","action_args":{"text":"hello"},"final_answer":null}',
            '{"thought":"The observation is enough.","action":null,"action_args":{},"final_answer":"hello"}',
        ]
    )

    result = ReActAgent(llm, registry, max_tool_calls=3).run("say hello")

    assert result.final_answer == "hello"
    assert result.trace is not None
    assert [step.step for step in result.trace.steps] == [
        "planner",
        "thought",
        "action",
        "tool_call",
        "observation",
        "thought",
        "final_answer",
    ]
    assert result.trace.steps[2].tool_name == "echo"
    assert result.trace.steps[2].metadata["turn"] == 1
    assert result.trace.steps[4].observation["result"] == {"text": "hello"}


def test_react_agent_rejects_unregistered_tool_without_executing_registry():
    llm = FakeLLM(
        [
            'Thought: I should use an unknown tool.\nAction: {"tool": "missing", "args": {"api_key": "sk-secret123"}}',
            "Final Answer: could not call the tool",
        ]
    )

    result = ReActAgent(llm, ToolRegistry()).run("test")

    assert len(llm.calls) == 2
    assert result.tool_calls[0].tool_name == "missing"
    assert result.tool_calls[0].status == "failed"
    assert result.tool_calls[0].error_code == TOOL_NOT_FOUND
    assert result.reasoning_steps[1].tool_args == {"api_key": "***"}
    assert result.reasoning_steps[-1].status == "unknown_tool"


def test_react_agent_caps_tool_calls_at_five_before_finalizing():
    registry = ToolRegistry()
    registry.register(EchoTool())
    replies = [
        'Thought: loop.\nAction: {"tool": "echo", "args": {"text": "again"}}'
        for _ in range(5)
    ]
    replies.append("Final Answer: stopped")
    llm = FakeLLM(replies)

    result = ReActAgent(llm, registry).run("loop")

    assert len(result.tool_calls) == 5
    assert result.final_answer == "基于已有观察结果回答: stopped"
    assert result.reasoning_steps[-1].status == "tool_limit_reached"


def test_react_agent_stops_before_repeating_same_failed_tool():
    registry = ToolRegistry()
    failing_tool = FailingTool()
    registry.register(failing_tool)
    llm = FakeLLM(
        [
            'Thought: try it.\nAction: {"tool": "fail", "args": {}}',
            'Thought: try it again.\nAction: {"tool": "fail", "args": {}}',
            "Final Answer: the tool failed, so I stopped",
        ]
    )

    result = ReActAgent(llm, registry, max_tool_calls=5).run("fail twice")

    assert failing_tool.calls == 1
    assert len(result.tool_calls) == 1
    assert result.reasoning_steps[-1].status == "repeated_failed_tool"
    assert [step.step for step in result.trace.steps].count("tool_call") == 1
    assert result.trace.steps[-2].step == "observation"
    assert result.trace.steps[-2].status == "skipped"


def test_react_agent_compacts_long_observation_payloads():
    registry = ToolRegistry()
    registry.register(LargeTool())
    llm = FakeLLM(
        [
            'Thought: get data.\nAction: {"tool": "large", "args": {}}',
            "Final Answer: compacted",
        ]
    )

    result = ReActAgent(llm, registry).run("large")

    observation = result.reasoning_steps[2].observation
    assert observation["result"]["truncated"] is True
    assert observation["result"]["original_length"] > 4000
    assert len(observation["result"]["summary"]) <= 2003


def test_backend_compatibility_import_exports_react_agent():
    assert BackendReActAgent is ReActAgent
