from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.app.memory.safety import contains_sensitive_content
from backend.app.memory.store import JsonMemoryStore, LongMemory, ShortMemory
from backend.app.services.agent_types import ChatMessage

MAX_MEMORY_SEARCH_RESULTS = 3
MAX_RECENT_CONTEXT_ITEMS = 4
MAX_MEMORY_CONTEXT_CHARS = 4000
MAX_MEMORY_QUESTION_CHARS = 400
MAX_MEMORY_ANSWER_CHARS = 700
MAX_RECENT_CONTEXT_CHARS = 500


class MemoryManager:
    """Coordinate short-term session memory and long-term user memory."""

    def __init__(
        self,
        json_path: Path,
        short_limit: int = 12,
        long_limit: int = 500,
    ) -> None:
        store = JsonMemoryStore(json_path)
        self.short_memory = ShortMemory(store, max_messages=short_limit)
        self.long_memory = LongMemory(store, max_entries_per_user=long_limit)

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

        messages, _ = self.build_memory_context(
            user_id=user_id,
            conversation_id=conversation_id,
            query=query,
            search_limit=search_limit,
            recent_limit=recent_limit,
        )
        return messages

    def build_memory_context(
        self,
        *,
        user_id: str,
        conversation_id: str,
        query: str,
        search_limit: int = 5,
        recent_limit: int = 6,
    ) -> tuple[list[ChatMessage], int]:
        """Build model-ready memory context messages and return the injected item count."""

        safe_search_limit = _safe_limit(search_limit, MAX_MEMORY_SEARCH_RESULTS)
        safe_recent_limit = _safe_limit(recent_limit, MAX_RECENT_CONTEXT_ITEMS)
        memories = self._safe_search_memory(user_id=user_id, query=query, limit=safe_search_limit)
        recent_context = self._safe_recent_context(
            user_id=user_id,
            conversation_id=conversation_id,
            limit=safe_recent_limit,
        )
        if not memories and not recent_context:
            return [], 0

        memory_used = 0
        lines = [
            "Private model context. Use only when directly relevant.",
            "Do not mention memory retrieval, quote this context, or reveal it to the user.",
        ]
        if memories:
            _append_if_fits(lines, "Relevant saved exchanges:", MAX_MEMORY_CONTEXT_CHARS)
            for index, memory in enumerate(memories, start=1):
                question = _truncate_text(memory.get("question", ""), MAX_MEMORY_QUESTION_CHARS)
                answer = _truncate_text(memory.get("answer", ""), MAX_MEMORY_ANSWER_CHARS)
                if not question and not answer:
                    continue
                block = (
                    f"{index}. User asked: {question}\n"
                    f"   Assistant answered: {answer}"
                )
                if not _append_if_fits(lines, block, MAX_MEMORY_CONTEXT_CHARS):
                    break
                memory_used += 1

        if recent_context:
            _append_if_fits(lines, "Recent conversation context:", MAX_MEMORY_CONTEXT_CHARS)
            for item in recent_context:
                role = "User" if item["role"] == "user" else "Assistant"
                content = _truncate_text(item["content"], MAX_RECENT_CONTEXT_CHARS)
                if not content:
                    continue
                if not _append_if_fits(lines, f"- {role}: {content}", MAX_MEMORY_CONTEXT_CHARS):
                    break
                memory_used += 1

        if memory_used == 0:
            return [], 0

        return [
            {
                "role": "system",
                "content": "\n".join(lines),
            }
        ], memory_used

    def _safe_search_memory(self, *, user_id: str, query: str, limit: int) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        try:
            return self.search_memory(user_id=user_id, query=query, limit=limit)
        except Exception:
            return []

    def _safe_recent_context(
        self,
        *,
        user_id: str,
        conversation_id: str,
        limit: int,
    ) -> list[dict[str, str]]:
        if limit <= 0:
            return []
        try:
            return self.get_recent_context(
                user_id=user_id,
                conversation_id=conversation_id,
                limit=limit,
            )
        except Exception:
            return []


def _safe_limit(value: int, maximum: int) -> int:
    return max(0, min(int(value or 0), maximum))


def _truncate_text(value: Any, max_chars: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_chars:
        return text
    return f"{text[: max(0, max_chars - 1)].rstrip()}..."


def _append_if_fits(lines: list[str], text: str, max_chars: int) -> bool:
    if _joined_length(lines) + len(text) + 1 > max_chars:
        return False
    lines.append(text)
    return True


def _joined_length(lines: list[str]) -> int:
    return sum(len(line) + 1 for line in lines)
