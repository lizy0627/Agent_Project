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


def test_react_agent_rejects_unregistered_tool_without_executing_registry():
    llm = FakeLLM(
        [
            'Thought: I should use an unknown tool.\nAction: {"tool": "missing", "args": {"api_key": "sk-secret123"}}',
            "Final Answer: could not call the tool",
        ]
    )

    result = ReActAgent(llm, ToolRegistry()).run("test")

    assert result.tool_calls[0].tool_name == "missing"
    assert result.tool_calls[0].status == "failed"
    assert result.tool_calls[0].error_code == TOOL_NOT_FOUND
    assert result.reasoning_steps[1].tool_args == {"api_key": "***"}


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
    assert result.final_answer == "stopped"
    assert result.reasoning_steps[-1].status == "tool_limit_reached"


def test_backend_compatibility_import_exports_react_agent():
    assert BackendReActAgent is ReActAgent
