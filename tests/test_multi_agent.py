import json
from typing import Any

from app.agents import ManagerAgent
from app.agents.base import AgentResult
from app.api.chat import resolve_agent_mode
from app.schemas.chat import ChatRequest
from app.tools.base import ToolResult
from backend.app.agents import ManagerAgent as BackendManagerAgent
from backend.app.api.chat import resolve_agent_mode as resolve_backend_agent_mode
from backend.app.schemas.chat import ChatRequest as BackendChatRequest


class FakeLLMClient:
    model = "fake-model"

    def complete_chat(self, messages, model=None):
        return "aggregated answer"


class FakeToolManager:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def call(self, name: str, max_retries: int = 1, **kwargs: Any) -> ToolResult:
        self.queries.append(kwargs["query"])
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


class RouterLLMClient:
    model = "fake-model"

    def complete_chat(self, messages, model=None):
        system_content = messages[0]["content"]
        if "ManagerAgent router" in system_content:
            return (
                '{"agents":[{"name":"SearchAgent","task":"Find current FastAPI release news",'
                '"reason":"The user asks for current external information."}]}'
            )
        return "aggregated answer"


class TwoAgentRouterLLMClient:
    model = "fake-model"

    def __init__(self) -> None:
        self.aggregate_payload: dict[str, Any] | None = None

    def complete_chat(self, messages, model=None):
        system_content = messages[0]["content"]
        if "ManagerAgent router" in system_content:
            return (
                '{"agents":['
                '{"name":"SearchAgent","task":"Search task","reason":"Needs search."},'
                '{"name":"CodeAgent","task":"Code task","reason":"Needs code."}'
                "]}"
            )
        self.aggregate_payload = json.loads(messages[1]["content"])
        return "aggregated from successful agents"


class RaisingAgent:
    def __init__(self, name: str) -> None:
        self.name = name

    def run(self, question, messages, model=None):
        raise RuntimeError(f"{self.name} failed hard")


class SuccessfulAgent:
    def __init__(self, name: str, content: str) -> None:
        self.name = name
        self.content = content

    def run(self, question, messages, model=None):
        return AgentResult(
            agent_name=self.name,
            task=question,
            success=True,
            content=self.content,
            data={"agent": self.name},
        )


def test_manager_selects_search_and_code_agents():
    manager = ManagerAgent(llm_client=FakeLLMClient(), tool_manager=FakeToolManager())

    selected = manager.select_agents("search latest FastAPI API code examples")

    assert [agent.name for agent in selected] == ["SearchAgent", "CodeAgent"]


def test_manager_plan_agents_uses_llm_router():
    manager = ManagerAgent(llm_client=RouterLLMClient(), tool_manager=FakeToolManager())

    plan = manager.plan_agents("what is new in FastAPI?")

    assert [item.agent.name for item in plan] == ["SearchAgent"]
    assert plan[0].task == "Find current FastAPI release news"
    assert plan[0].reason == "The user asks for current external information."
    assert plan[0].source == "llm_router"


def test_manager_plan_agents_falls_back_for_invalid_router_json():
    manager = ManagerAgent(llm_client=FakeLLMClient(), tool_manager=FakeToolManager())

    plan = manager.plan_agents("search latest FastAPI API code examples")

    assert [item.agent.name for item in plan] == ["SearchAgent", "CodeAgent"]
    assert [item.source for item in plan] == ["keyword_fallback", "keyword_fallback"]


def test_manager_returns_structured_sub_agent_trace():
    tool_manager = FakeToolManager()
    manager = ManagerAgent(llm_client=RouterLLMClient(), tool_manager=tool_manager)

    reply = manager.chat([{"role": "user", "content": "search latest FastAPI news"}])

    assert reply.content == "aggregated answer"
    assert tool_manager.queries == ["Find current FastAPI release news"]
    manager_steps = [step for step in reply.trace if step.step == "manager_plan"]
    assert manager_steps[0].metadata["router"] == "llm_router"
    assert manager_steps[0].metadata["tasks"][0]["task"] == "Find current FastAPI release news"
    assert [step.step for step in reply.trace] == [
        "manager_plan",
        "sub_agent_start",
        "sub_agent_result",
        "aggregate_final",
    ]
    sub_agent_results = [step for step in reply.trace if step.step == "sub_agent_result"]
    assert sub_agent_results[0].observation["agent_name"] == "SearchAgent"
    assert sub_agent_results[0].observation["task"] == "Find current FastAPI release news"
    assert sub_agent_results[0].observation["success"] is True
    final_steps = [step for step in reply.trace if step.step == "aggregate_final"]
    assert final_steps[0].observation == {"content": "aggregated answer"}


def test_manager_keeps_running_when_one_sub_agent_raises_and_aggregates_successes():
    llm_client = TwoAgentRouterLLMClient()
    manager = ManagerAgent(
        llm_client=llm_client,
        tool_manager=FakeToolManager(),
        search_agent=RaisingAgent("SearchAgent"),
        code_agent=SuccessfulAgent("CodeAgent", "code evidence"),
    )

    reply = manager.chat([{"role": "user", "content": "search latest API code"}])

    assert reply.content == "aggregated from successful agents"
    result_steps = [step for step in reply.trace if step.step == "sub_agent_result"]
    assert [step.status for step in result_steps] == ["failed", "success"]
    assert llm_client.aggregate_payload is not None
    assert [item["agent_name"] for item in llm_client.aggregate_payload["successful_sub_agent_results"]] == ["CodeAgent"]
    assert [item["agent_name"] for item in llm_client.aggregate_payload["failed_sub_agent_results"]] == ["SearchAgent"]
    final_steps = [step for step in reply.trace if step.step == "aggregate_final"]
    assert final_steps[0].metadata["successful_sub_agents"] == ["CodeAgent"]


def test_manager_returns_friendly_error_when_all_sub_agents_fail():
    manager = ManagerAgent(
        llm_client=TwoAgentRouterLLMClient(),
        tool_manager=FakeToolManager(),
        search_agent=RaisingAgent("SearchAgent"),
        code_agent=RaisingAgent("CodeAgent"),
    )

    reply = manager.chat([{"role": "user", "content": "search latest API code"}])

    assert "every selected sub-agent failed" in reply.content
    final_steps = [step for step in reply.trace if step.step == "aggregate_final"]
    assert final_steps[0].status == "failed"


def test_backend_manager_plan_agents_falls_back_for_invalid_router_json():
    manager = BackendManagerAgent(llm_client=FakeLLMClient(), tool_manager=FakeToolManager())

    plan = manager.plan_agents("search latest FastAPI API code examples")

    assert [item.agent.name for item in plan] == ["SearchAgent", "CodeAgent"]
    assert [item.source for item in plan] == ["keyword_fallback", "keyword_fallback"]


def test_chat_request_accepts_multi_agent_flag():
    request = ChatRequest(message="hello", multi_agent=True)

    assert request.multi_agent is True


def test_chat_request_accepts_multi_agent_agent_mode():
    request = ChatRequest(message="hello", agent_mode="multi_agent")

    assert request.agent_mode == "multi_agent"
    assert request.multi_agent is False
    assert resolve_agent_mode(request) == "multi_agent"


def test_multi_agent_flag_overrides_agent_mode_for_compatibility():
    request = ChatRequest(message="hello", multi_agent=True, agent_mode="react")

    assert resolve_agent_mode(request) == "multi_agent"


def test_backend_chat_request_uses_same_agent_mode_compatibility_rule():
    request = BackendChatRequest(message="hello", multi_agent=True, agent_mode="react")

    assert resolve_backend_agent_mode(request) == "multi_agent"
