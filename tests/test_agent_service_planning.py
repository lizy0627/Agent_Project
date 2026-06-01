import pytest

from app.agent.planner import AgentPlan, PlanStep
from app.config.settings import Settings
from app.services.agent_service import AgentService
from app.tools.tool_manager import ToolManager


class CountingLLMPlanner:
    def __init__(self, plan: AgentPlan | None = None, error: Exception | None = None) -> None:
        self.plan = plan
        self.error = error
        self.calls = 0

    def generate(self, messages):
        self.calls += 1
        if self.error is not None:
            raise self.error
        if self.plan is None:
            raise AssertionError("No fake plan configured.")
        return self.plan


@pytest.fixture
def agent_service() -> AgentService:
    return AgentService(Settings(mcp_enabled=False), tool_manager=ToolManager())


def direct_plan(question: str) -> AgentPlan:
    return AgentPlan(
        question=question,
        steps=[
            PlanStep(
                step_id="direct_answer",
                description="Answer directly.",
                tool_name=None,
                tool_args={},
                depends_on=[],
            )
        ],
    )


def test_simple_direct_chat_skips_llm_planner(agent_service: AgentService):
    fake_llm = CountingLLMPlanner(error=AssertionError("LLM planner should not be called."))
    agent_service.llm_planner = fake_llm
    trace = []

    planned_call, plan = agent_service._trace_plan_tool_call([{"role": "user", "content": "你好"}], trace)

    assert planned_call is None
    assert plan.steps[0].step_id == "direct_answer"
    assert fake_llm.calls == 0
    assert trace[0].metadata["planner_source"] == "simple_direct"


@pytest.mark.parametrize("message", ["hi there", "good morning", "谢谢你", "讲个笑话"])
def test_common_small_talk_uses_simple_direct(agent_service: AgentService, message: str):
    assert agent_service._looks_like_simple_direct_chat([{"role": "user", "content": message}]) is True


def test_non_simple_chat_uses_llm_planner(agent_service: AgentService):
    fake_llm = CountingLLMPlanner(plan=direct_plan("搜索 Python 最新版本"))
    agent_service.llm_planner = fake_llm
    trace = []

    planned_call, plan = agent_service._trace_plan_tool_call(
        [{"role": "user", "content": "搜索 Python 最新版本"}],
        trace,
    )

    assert planned_call is None
    assert plan.question == "搜索 Python 最新版本"
    assert fake_llm.calls == 1
    assert trace[0].metadata["planner_source"] == "llm_planner"


def test_llm_planner_failure_falls_back_to_rule_planner(agent_service: AgentService):
    fake_llm = CountingLLMPlanner(error=ValueError("bad planner json"))
    agent_service.llm_planner = fake_llm
    trace = []

    planned_call, plan = agent_service._trace_plan_tool_call(
        [{"role": "user", "content": "2 + 2 等于多少"}],
        trace,
    )

    assert planned_call is not None
    assert planned_call.name == "calculate"
    assert plan.steps[0].tool_name == "calculate"
    assert fake_llm.calls == 1
    assert trace[0].metadata["planner_source"] == "rule_fallback"


def test_trace_exposes_planner_source_and_plan_step_fields(agent_service: AgentService):
    fake_llm = CountingLLMPlanner(
        plan=AgentPlan(
            question="call missing tool",
            steps=[
                PlanStep(
                    step_id="tool_1",
                    description="Call a tool.",
                    tool_name="missing_tool",
                    tool_args={"value": "x"},
                    depends_on=[],
                ),
                PlanStep(
                    step_id="final_answer",
                    description="Answer from tool output.",
                    tool_name=None,
                    tool_args={},
                    depends_on=["tool_1"],
                ),
            ],
        )
    )
    agent_service.llm_planner = fake_llm
    trace = []

    _planned_call, plan = agent_service._trace_plan_tool_call(
        [{"role": "user", "content": "use a tool for this"}],
        trace,
    )
    executor_trace = agent_service.executor.execute(plan)
    agent_service._append_executor_trace(trace, executor_trace)

    assert trace[0].metadata["planner_source"] == "llm_planner"
    assert trace[1].to_dict()["step_id"] == "tool_1"
    assert trace[1].to_dict()["depends_on"] == []
    assert trace[3].to_dict()["step_id"] == "final_answer"
    assert trace[3].to_dict()["depends_on"] == ["tool_1"]


@pytest.mark.parametrize(
    "message",
    [
        "最新的 Python 版本是什么？",
        "今天北京天气怎么样？",
        "查一下美元人民币汇率",
        "帮我搜索一下 OpenAI 新闻",
        "OpenAI news",
        "2 + 2 等于多少？",
        "现在几点？",
        "读取这个网页 https://example.com",
        "调用 MCP 工具查一下模型",
        "先总结这段文字，然后翻译成英文",
    ],
)
def test_planner_needed_messages_do_not_use_simple_direct(agent_service: AgentService, message: str):
    assert agent_service._looks_like_simple_direct_chat([{"role": "user", "content": message}]) is False
