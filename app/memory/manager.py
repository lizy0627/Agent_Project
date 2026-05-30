from __future__ import annotations

from pathlib import Path
from typing import Any

from app.memory.safety import contains_sensitive_content
from app.memory.store import JsonMemoryStore, LongMemory, ShortMemory
from app.memory.vector_store import EmbeddingProviderProtocol
from app.services.agent_types import ChatMessage


class MemoryManager:
    """Coordinate short-term session memory and long-term user memory."""

    def __init__(
        self,
        json_path: Path,
        short_limit: int = 12,
        long_limit: int = 500,
        *,
        vector_enabled: bool = False,
        vector_top_k: int = 5,
        embedding_provider: EmbeddingProviderProtocol | None = None,
    ) -> None:
        store = JsonMemoryStore(json_path)
        self.short_memory = ShortMemory(store, max_messages=short_limit)
        self.long_memory = LongMemory(
            store,
            max_entries_per_user=long_limit,
            embedding_provider=embedding_provider,
            vector_enabled=vector_enabled,
            vector_top_k=vector_top_k,
        )

    def add_memory(
        self,
        *,
        user_id: str,
        conversation_id: str,
        question: str,
        answer: str,
    ) -> dict[str, Any] | None:
        """Save an exchange into short-term and long-term memory when safe."""

        if contains_sensitive_content(question, answer):
            return None

        self.short_memory.append_message(user_id, conversation_id, "user", question)
        self.short_memory.append_message(user_id, conversation_id, "assistant", answer)
        return self.long_memory.add_exchange(user_id, conversation_id, question, answer)

    def search_memory(self, *, user_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search historical memories for one user."""

        return self.long_memory.search(user_id, query, limit=limit)

    def get_recent_context(
        self,
        *,
        user_id: str,
        conversation_id: str,
        limit: int = 6,
    ) -> list[dict[str, str]]:
        """Return recent short-term context for the current conversation."""

        return self.short_memory.get_recent_context(user_id, conversation_id, limit=limit)

    def build_memory_messages(
        self,
        *,
        user_id: str,
        conversation_id: str,
        query: str,
        search_limit: int = 5,
        recent_limit: int = 6,
    ) -> list[ChatMessage]:
        """Build model-ready memory context messages."""

        memories = self.search_memory(user_id=user_id, query=query, limit=search_limit)
        recent_context = self.get_recent_context(
            user_id=user_id,
            conversation_id=conversation_id,
            limit=recent_limit,
        )
        if not memories and not recent_context:
            return []

        lines = [
            "以下是系统自动检索到的用户记忆，仅用于补充上下文。",
            "如果记忆与当前问题无关，请忽略；不要主动暴露记忆库内容。",
        ]
        if memories:
            lines.append("相关历史问答：")
            for index, memory in enumerate(memories, start=1):
                lines.append(
                    f"{index}. 用户曾问：{memory.get('question', '')}\n"
                    f"   当时回答：{memory.get('answer', '')}"
                )

        if recent_context:
            lines.append("当前会话近期上下文：")
            for item in recent_context:
                role = "用户" if item["role"] == "user" else "助手"
                lines.append(f"- {role}: {item['content']}")

        return [
            {
                "role": "system",
                "content": "\n".join(lines),
            }
        ]
