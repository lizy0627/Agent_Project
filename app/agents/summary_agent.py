from __future__ import annotations

from time import perf_counter

from app.agents.base import AgentResult, BaseAgent, LLMClientProtocol
from app.services.agent_types import ChatMessage


class SummaryAgent(BaseAgent):
    """Sub agent responsible for concise summarization."""

    name = "SummaryAgent"

    def __init__(self, llm_client: LLMClientProtocol) -> None:
        self.llm_client = llm_client

    def run(self, question: str, messages: list[ChatMessage], model: str | None = None) -> AgentResult:
        started_at = perf_counter()
        task = question.strip() or "Summarize the user's request and any provided context into key points."
        source_text = self._source_text(task, messages)
        try:
            content = self.llm_client.complete_chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are SummaryAgent. Extract the key points, intent, constraints, "
                            "and requested output. Be concise and preserve important details."
                        ),
                    },
                    {"role": "user", "content": source_text},
                ],
                model=model,
            )
        except Exception as exc:
            return AgentResult(
                agent_name=self.name,
                task=task,
                success=False,
                content="SummaryAgent could not complete the summary.",
                error=str(exc),
                duration_ms=self._elapsed_ms(started_at),
                metadata={"source_chars": len(source_text)},
            )

        return AgentResult(
            agent_name=self.name,
            task=task,
            success=True,
            content=content,
            duration_ms=self._elapsed_ms(started_at),
            metadata={"source_chars": len(source_text)},
        )

    def _source_text(self, question: str, messages: list[ChatMessage]) -> str:
        sections = []
        if question:
            sections.append(f"task: {question}")

        history = []
        for message in messages[-6:]:
            role = message.get("role", "")
            content = message.get("content", "")
            if role and content:
                history.append(f"{role}: {content}")
        if history:
            sections.append("conversation:\n" + "\n".join(history))

        return "\n\n".join(sections) or question
