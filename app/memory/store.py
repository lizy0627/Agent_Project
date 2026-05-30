from __future__ import annotations

import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from app.memory.safety import contains_sensitive_content, normalize_memory_text
from app.memory.vector_store import EmbeddingProviderProtocol, LocalVectorStore, memory_embedding_text


DEFAULT_SHORT_LIMIT = 12
DEFAULT_LONG_LIMIT = 500


class JsonMemoryStore:
    """Small JSON-backed store shared by short-term and long-term memory."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = RLock()

    def read(self) -> dict[str, Any]:
        with self.lock:
            if not self.path.exists():
                return {"short": {}, "long": {}}

            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {"short": {}, "long": {}}

            if not isinstance(data, dict):
                return {"short": {}, "long": {}}
            data.setdefault("short", {})
            data.setdefault("long", {})
            return data

    def write(self, data: dict[str, Any]) -> None:
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
            temp_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temp_path.replace(self.path)

    def update(self, callback) -> Any:
        with self.lock:
            data = self.read()
            result = callback(data)
            self.write(data)
            return result


class ShortMemory:
    """Save bounded current-session context by user and conversation."""

    def __init__(self, store: JsonMemoryStore, max_messages: int = DEFAULT_SHORT_LIMIT) -> None:
        self.store = store
        self.max_messages = max_messages

    def append_message(self, user_id: str, conversation_id: str, role: str, content: str) -> bool:
        if not self._can_store(content):
            return False

        message = {
            "role": role,
            "content": normalize_memory_text(content, 1200),
            "created_at": utc_now(),
        }

        def update(data: dict[str, Any]) -> bool:
            conversations = data.setdefault("short", {}).setdefault(user_id, {})
            messages = conversations.setdefault(conversation_id, [])
            messages.append(message)
            conversations[conversation_id] = messages[-self.max_messages :]
            return True

        return bool(self.store.update(update))

    def get_recent_context(self, user_id: str, conversation_id: str, limit: int = 6) -> list[dict[str, str]]:
        data = self.store.read()
        messages = data.get("short", {}).get(user_id, {}).get(conversation_id, [])
        if not isinstance(messages, list):
            return []

        context: list[dict[str, str]] = []
        for item in messages[-limit:]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip()
            content = str(item.get("content") or "").strip()
            if role and content:
                context.append({"role": role, "content": content})
        return context

    def _can_store(self, content: str) -> bool:
        return bool(str(content or "").strip()) and not contains_sensitive_content(content)


class LongMemory:
    """Save and retrieve useful historical user-assistant exchanges."""

    def __init__(
        self,
        store: JsonMemoryStore,
        max_entries_per_user: int = DEFAULT_LONG_LIMIT,
        *,
        embedding_provider: EmbeddingProviderProtocol | None = None,
        vector_enabled: bool = False,
        vector_top_k: int = 5,
        vector_store: LocalVectorStore | None = None,
    ) -> None:
        self.store = store
        self.max_entries_per_user = max_entries_per_user
        self.embedding_provider = embedding_provider
        self.vector_enabled = vector_enabled
        self.vector_top_k = vector_top_k
        self.vector_store = vector_store or LocalVectorStore()

    def add_exchange(
        self,
        user_id: str,
        conversation_id: str,
        question: str,
        answer: str,
    ) -> dict[str, Any] | None:
        if not self._should_store(question, answer):
            return None

        clean_question = normalize_memory_text(question, 1000)
        clean_answer = normalize_memory_text(answer, 1800)
        entry = {
            "id": str(uuid4()),
            "user_id": user_id,
            "conversation_id": conversation_id,
            "question": clean_question,
            "answer": clean_answer,
            "embedding": self._embedding_for(clean_question, clean_answer),
            "keywords": sorted(tokenize(f"{question} {answer}"))[:40],
            "created_at": utc_now(),
        }

        def update(data: dict[str, Any]) -> dict[str, Any]:
            user_memories = data.setdefault("long", {}).setdefault(user_id, [])
            user_memories.append(entry)
            data["long"][user_id] = user_memories[-self.max_entries_per_user :]
            return entry

        return self.store.update(update)

    def search(self, user_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        data = self.store.read()
        entries = data.get("long", {}).get(user_id, [])
        if not isinstance(entries, list):
            return []
        valid_entries = [entry for entry in entries if isinstance(entry, dict)]

        vector_results = self._vector_search(valid_entries, query, limit)
        if vector_results:
            return vector_results

        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        scored: list[tuple[float, dict[str, Any]]] = []
        for entry in valid_entries:
            score = memory_score(query_tokens, entry)
            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda item: (item[0], item[1].get("created_at", "")), reverse=True)
        results: list[dict[str, Any]] = []
        for score, entry in scored[:limit]:
            item = dict(entry)
            item["score"] = round(score, 4)
            results.append(item)
        return results

    def _should_store(self, question: str, answer: str) -> bool:
        clean_question = str(question or "").strip()
        clean_answer = str(answer or "").strip()
        if len(clean_question) < 8 or len(clean_answer) < 8:
            return False
        if contains_sensitive_content(clean_question, clean_answer):
            return False
        return True

    def _embedding_for(self, question: str, answer: str) -> list[float] | None:
        if not self.vector_enabled or self.embedding_provider is None:
            return None
        return self.embedding_provider.embed(memory_embedding_text(question, answer))

    def _vector_search(self, entries: list[dict[str, Any]], query: str, limit: int) -> list[dict[str, Any]]:
        if not self.vector_enabled or self.embedding_provider is None:
            return []

        query_embedding = self.embedding_provider.embed(query)
        if not query_embedding:
            return []

        vector_limit = max(1, min(limit, self.vector_top_k))
        results = self.vector_store.search(entries, query_embedding, limit=vector_limit)
        if not results:
            return []

        payload: list[dict[str, Any]] = []
        for result in results:
            item = dict(result.entry)
            item["score"] = round(result.score, 4)
            item["score_type"] = "vector"
            payload.append(item)
        return payload


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def tokenize(text: str) -> set[str]:
    """Tokenize mixed Chinese/English text for lightweight local search."""

    lowered = str(text or "").lower()
    tokens = set(re.findall(r"[a-z0-9_]{2,}", lowered))
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", lowered)
    tokens.update(chinese_chars)
    tokens.update("".join(chinese_chars[index : index + 2]) for index in range(max(0, len(chinese_chars) - 1)))
    return {token for token in tokens if token.strip()}


def memory_score(query_tokens: set[str], entry: dict[str, Any]) -> float:
    entry_tokens = set(entry.get("keywords") or [])
    if not entry_tokens:
        entry_tokens = tokenize(f"{entry.get('question', '')} {entry.get('answer', '')}")

    overlap = query_tokens & entry_tokens
    if not overlap:
        return 0.0

    recency_bonus = 0.0
    created_at = str(entry.get("created_at") or "")
    try:
        created = datetime.fromisoformat(created_at)
        days_old = max(0.0, (datetime.now(UTC) - created).total_seconds() / 86400)
        recency_bonus = 1 / (1 + math.log1p(days_old))
    except ValueError:
        recency_bonus = 0.0

    return len(overlap) / math.sqrt(max(1, len(query_tokens))) + recency_bonus * 0.1
