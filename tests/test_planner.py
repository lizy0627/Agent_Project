from app.agent.planner import Planner


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
