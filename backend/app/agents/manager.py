from __future__ import annotations

import json
from time import perf_counter

from backend.app.agents.base import AgentResult, BaseAgent, LLMClientProtocol
from backend.app.agents.code_agent import CodeAgent
from backend.app.agents.search_agent import SearchAgent, ToolManagerProtocol
from backend.app.agents.summary_agent import SummaryAgent
from backend.app.services.agent_types import AgentReply, AgentTraceStep, ChatMessage


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
        selected_agents = self.select_agents(question)
        tasks = [agent.name for agent in selected_agents]
        trace: list[AgentTraceStep] = [
            AgentTraceStep(
                step="multi_agent_manager",
                status="success",
                message=f"Selected agents: {', '.join(tasks)}",
                duration_ms=self._elapsed_ms(started_at),
                metadata={
                    "manager": self.name,
                    "tasks": [{"agent_name": agent.name, "task": self._task_for_agent(agent.name)} for agent in selected_agents],
                },
            )
        ]

        results: list[AgentResult] = []
        for agent in selected_agents:
            result = agent.run(question, messages, model=model)
            results.append(result)
            trace.append(
                AgentTraceStep(
                    step="multi_agent_sub_agent",
                    status="success" if result.success else "failed",
                    message=result.error or result.task,
                    tool_name=result.agent_name,
                    observation=result.to_dict(),
                    duration_ms=result.duration_ms,
                    metadata={"agent_name": result.agent_name},
                )
            )

        final_started_at = perf_counter()
        content = self._aggregate(question, messages, results, model=model)
        trace.append(
            AgentTraceStep(
                step="final_answer",
                status="success",
                message="ManagerAgent aggregated sub-agent results.",
                duration_ms=self._elapsed_ms(final_started_at),
                metadata={
                    "manager": self.name,
                    "sub_agents": [result.agent_name for result in results],
                },
            )
        )
        return AgentReply(content=content, trace=trace)

    def select_agents(self, question: str) -> list[SearchAgent | SummaryAgent | CodeAgent]:
        lowered = question.lower()
        selected: list[SearchAgent | SummaryAgent | CodeAgent] = []
        if any(keyword in lowered for keyword in SEARCH_KEYWORDS):
            selected.append(self.search_agent)
        if any(keyword in lowered for keyword in CODE_KEYWORDS):
            selected.append(self.code_agent)
        if any(keyword in lowered for keyword in SUMMARY_KEYWORDS) or len(question) >= 1000:
            selected.append(self.summary_agent)
        if not selected:
            selected.append(self.summary_agent)
        return selected

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
