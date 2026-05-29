from typing import Any

from app.agents import ManagerAgent
from app.schemas.chat import ChatRequest
from app.tools.base import ToolResult


class FakeLLMClient:
    model = "fake-model"

    def complete_chat(self, messages, model=None):
        return "aggregated answer"


class FakeToolManager:
    def call(self, name: str, max_retries: int = 1, **kwargs: Any) -> ToolResult:
        return ToolResult(
            name=name,
            success=True,
            result={
                "query": kwargs["query"],
                "results": [
                    {
                        "title": "Example result",
                        "url": "https://example.test",
                        "content": "Example snippet",
                    }
                ],
            },
            duration_ms=1.0,
        )


def test_manager_selects_search_and_code_agents():
    manager = ManagerAgent(llm_client=FakeLLMClient(), tool_manager=FakeToolManager())

    selected = manager.select_agents("search latest FastAPI API code examples")

    assert [agent.name for agent in selected] == ["SearchAgent", "CodeAgent"]


def test_manager_returns_structured_sub_agent_trace():
    manager = ManagerAgent(llm_client=FakeLLMClient(), tool_manager=FakeToolManager())

    reply = manager.chat([{"role": "user", "content": "search latest FastAPI news"}])

    assert reply.content == "aggregated answer"
    sub_agent_steps = [step for step in reply.trace if step.step == "multi_agent_sub_agent"]
    assert sub_agent_steps
    assert sub_agent_steps[0].observation["agent_name"] == "SearchAgent"
    assert sub_agent_steps[0].observation["success"] is True


def test_chat_request_accepts_multi_agent_flag():
    request = ChatRequest(message="hello", multi_agent=True)

    assert request.multi_agent is True
