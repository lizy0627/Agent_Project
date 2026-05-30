from __future__ import annotations

from dataclasses import dataclass
import json
from time import perf_counter

from app.agents.base import AgentResult, BaseAgent, LLMClientProtocol
from app.agents.code_agent import CodeAgent
from app.agents.search_agent import SearchAgent, ToolManagerProtocol
from app.agents.summary_agent import SummaryAgent
from app.services.agent_types import AgentReply, AgentTraceStep, ChatMessage


SEARCH_KEYWORDS = (
    "search",
    "latest",
    "news",
    "current",
    "recent",
    "website",
    "official",
    "price",
    "github",
    "paper",
    "\u641c\u7d22",
    "\u8054\u7f51",
    "\u6700\u65b0",
    "\u65b0\u95fb",
    "\u8d44\u6599",
    "\u5b98\u7f51",
    "\u6700\u8fd1",
    "\u4ef7\u683c",
    "\u8bba\u6587",
)
SUMMARY_KEYWORDS = (
    "summary",
    "summarize",
    "summarise",
    "\u603b\u7ed3",
    "\u6458\u8981",
    "\u6982\u62ec",
    "\u5f52\u7eb3",
    "\u63d0\u70bc",
)
CODE_KEYWORDS = (
    "code",
    "bug",
    "debug",
    "error",
    "exception",
    "api",
    "function",
    "class",
    "python",
    "javascript",
    "typescript",
    "fastapi",
    "sql",
    "\u4ee3\u7801",
    "\u51fd\u6570",
    "\u7c7b",
    "\u62a5\u9519",
    "\u9519\u8bef",
    "\u5f02\u5e38",
    "\u63a5\u53e3",
    "\u5b9e\u73b0",
    "\u91cd\u6784",
    "\u6d4b\u8bd5",
    "\u6570\u636e\u5e93",
)


SubAgent = SearchAgent | SummaryAgent | CodeAgent


@dataclass(frozen=True)
class AgentPlanItem:
    """One ManagerAgent routing decision."""

    agent: SubAgent
    task: str
    reason: str
    source: str


class ManagerAgent(BaseAgent):
    """Decompose a user request, dispatch sub agents, and aggregate the final answer."""

    name = "ManagerAgent"

    def __init__(
        self,
        llm_client: LLMClientProtocol,
        tool_manager: ToolManagerProtocol,
        search_agent: SearchAgent | None = None,
        summary_agent: SummaryAgent | None = None,
        code_agent: CodeAgent | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.search_agent = search_agent or SearchAgent(tool_manager)
        self.summary_agent = summary_agent or SummaryAgent(llm_client)
        self.code_agent = code_agent or CodeAgent(llm_client)

    def chat(self, messages: list[ChatMessage], model: str | None = None) -> AgentReply:
        started_at = perf_counter()
        question = self._latest_user_message(messages)
        plan = self.plan_agents(question, messages, model=model)
        tasks = [item.agent.name for item in plan]
        trace: list[AgentTraceStep] = [
            AgentTraceStep(
                step="multi_agent_manager",
                status="success",
                message=f"Planned agents: {', '.join(tasks)}",
                duration_ms=self._elapsed_ms(started_at),
                metadata={
                    "manager": self.name,
                    "router": plan[0].source if plan else "none",
                    "tasks": [
                        {
                            "agent_name": item.agent.name,
                            "task": item.task,
                            "reason": item.reason,
                            "source": item.source,
                        }
                        for item in plan
                    ],
                },
            )
        ]

        results: list[AgentResult] = []
        for item in plan:
            result = item.agent.run(item.task, messages, model=model)
            results.append(result)
            trace.append(
                AgentTraceStep(
                    step="multi_agent_sub_agent",
                    status="success" if result.success else "failed",
                    message=result.error or result.task,
                    tool_name=result.agent_name,
                    observation=result.to_dict(),
                    duration_ms=result.duration_ms,
                    metadata={
                        "agent_name": result.agent_name,
                        "task": item.task,
                        "reason": item.reason,
                    },
                )
            )

        final_started_at = perf_counter()
        content = self._aggregate(question, messages, results, model=model)
        trace.append(
            AgentTraceStep(
                step="final_answer",
                status="success",
                message="ManagerAgent aggregated sub-agent results.",
                observation={"content": content},
                duration_ms=self._elapsed_ms(final_started_at),
                metadata={
                    "manager": self.name,
                    "sub_agents": [result.agent_name for result in results],
                },
            )
        )
        return AgentReply(content=content, trace=trace)

    def plan_agents(
        self,
        question: str,
        messages: list[ChatMessage] | None = None,
        model: str | None = None,
    ) -> list[AgentPlanItem]:
        """Use an LLM router to plan sub-agent calls, with keyword selection as fallback."""

        try:
            raw_plan = self.llm_client.complete_chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are the ManagerAgent router. Choose which sub agents should handle "
                            "the user request. Return only valid JSON matching this schema: "
                            '{"agents":[{"name":"SearchAgent","task":"...","reason":"..."}]}. '
                            "Allowed agent names are exactly SearchAgent, SummaryAgent, and CodeAgent. "
                            "Use SearchAgent for external, current, source-backed, or web information. "
                            "Use CodeAgent for software, code, debugging, APIs, architecture, or tests. "
                            "Use SummaryAgent for summarization, extraction, long context, or general "
                            "synthesis. Select at least one agent and give each a concrete task."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "question": question,
                                "recent_messages": self._recent_messages(messages or []),
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
                model=model,
            )
            return self._parse_agent_plan(raw_plan)
        except Exception:
            return self._fallback_agent_plan(question)

    def select_agents(self, question: str) -> list[SubAgent]:
        lowered = question.lower()
        selected: list[SubAgent] = []
        if any(keyword in lowered for keyword in SEARCH_KEYWORDS):
            selected.append(self.search_agent)
        if any(keyword in lowered for keyword in CODE_KEYWORDS):
            selected.append(self.code_agent)
        if any(keyword in lowered for keyword in SUMMARY_KEYWORDS) or len(question) >= 1000:
            selected.append(self.summary_agent)
        if not selected:
            selected.append(self.summary_agent)
        return selected

    def _parse_agent_plan(self, raw_plan: str) -> list[AgentPlanItem]:
        payload = json.loads(raw_plan)
        agents = payload.get("agents") if isinstance(payload, dict) else None
        if not isinstance(agents, list) or not agents:
            raise ValueError("Router response must include a non-empty agents list.")

        plan: list[AgentPlanItem] = []
        seen_names: set[str] = set()
        for item in agents:
            if not isinstance(item, dict):
                raise ValueError("Router agent entries must be objects.")
            name = item.get("name")
            task = item.get("task")
            reason = item.get("reason")
            if not isinstance(name, str) or name not in self._agent_map():
                raise ValueError("Router selected an unsupported agent.")
            if name in seen_names:
                raise ValueError("Router selected the same agent more than once.")
            if not isinstance(task, str) or not task.strip():
                raise ValueError("Router agent task must be a non-empty string.")
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError("Router agent reason must be a non-empty string.")
            seen_names.add(name)
            plan.append(
                AgentPlanItem(
                    agent=self._agent_map()[name],
                    task=task.strip(),
                    reason=reason.strip(),
                    source="llm_router",
                )
            )

        return plan

    def _fallback_agent_plan(self, question: str) -> list[AgentPlanItem]:
        task = question.strip() or "Handle the user request."
        return [
            AgentPlanItem(
                agent=agent,
                task=task,
                reason="LLM router returned an invalid plan; selected by keyword fallback.",
                source="keyword_fallback",
            )
            for agent in self.select_agents(question)
        ]

    def _agent_map(self) -> dict[str, SubAgent]:
        return {
            "SearchAgent": self.search_agent,
            "SummaryAgent": self.summary_agent,
            "CodeAgent": self.code_agent,
        }

    def _recent_messages(self, messages: list[ChatMessage]) -> list[ChatMessage]:
        return [
            {"role": message.get("role", ""), "content": message.get("content", "")}
            for message in messages[-6:]
            if message.get("role") and message.get("content")
        ]

    def _aggregate(
        self,
        question: str,
        messages: list[ChatMessage],
        results: list[AgentResult],
        model: str | None = None,
    ) -> str:
        result_payload = [result.to_dict() for result in results]
        prompt = {
            "question": question,
            "sub_agent_results": result_payload,
        }
        try:
            return self.llm_client.complete_chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are ManagerAgent. Produce the final answer by combining structured "
                            "sub-agent results. Answer in the user's language. Be direct, cite search "
                            "sources when SearchAgent returned URLs, and briefly mention failed agents "
                            "only when the failure affects the answer."
                        ),
                    },
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
                model=model,
            )
        except Exception:
            return self._fallback_answer(results)

    def _fallback_answer(self, results: list[AgentResult]) -> str:
        successful = [result for result in results if result.success and result.content]
        if successful:
            return "\n\n".join(result.content for result in successful)

        errors = [result.error for result in results if result.error]
        if errors:
            return "Multi-agent mode could not complete the request: " + "; ".join(errors)
        return "Multi-agent mode did not produce a usable result."

    def _task_for_agent(self, agent_name: str) -> str:
        return {
            "SearchAgent": "Search external materials.",
            "SummaryAgent": "Summarize the request and context.",
            "CodeAgent": "Analyze code-related aspects.",
        }.get(agent_name, "Handle a subtask.")
