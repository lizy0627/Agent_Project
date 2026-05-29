from __future__ import annotations

from time import perf_counter

from app.agents.base import AgentResult, BaseAgent, LLMClientProtocol
from app.services.agent_types import ChatMessage


class CodeAgent(BaseAgent):
    """Sub agent responsible for code-oriented question analysis."""

    name = "CodeAgent"

    def __init__(self, llm_client: LLMClientProtocol) -> None:
        self.llm_client = llm_client

    def run(self, question: str, messages: list[ChatMessage], model: str | None = None) -> AgentResult:
        started_at = perf_counter()
        task = "Analyze code-related requirements, bugs, APIs, architecture, or implementation details."
        try:
            content = self.llm_client.complete_chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are CodeAgent. Analyze code-related questions with engineering judgment. "
                            "Identify likely causes, implementation steps, risks, and tests. "
                            "If repository context is missing, state what should be inspected."
                        ),
                    },
                    {"role": "user", "content": question},
                ],
                model=model,
            )
        except Exception as exc:
            return AgentResult(
                agent_name=self.name,
                task=task,
                success=False,
                content="CodeAgent could not complete the code analysis.",
                error=str(exc),
                duration_ms=self._elapsed_ms(started_at),
            )

        return AgentResult(
            agent_name=self.name,
            task=task,
            success=True,
            content=content,
            duration_ms=self._elapsed_ms(started_at),
            metadata={"analysis_type": "code"},
        )
