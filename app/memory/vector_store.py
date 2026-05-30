from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Protocol

from openai import OpenAI

from app.memory.safety import contains_sensitive_content, normalize_memory_text

try:
    import numpy as np
except Exception:  # pragma: no cover - numpy is optional for lightweight installs.
    np = None


DEFAULT_MEMORY_EMBEDDING_MODEL = "text-embedding-v4"


class EmbeddingProviderProtocol(Protocol):
    """Minimal protocol LongMemory needs from an embedding provider."""

    def embed(self, text: str) -> list[float] | None:
        """Return an embedding vector, or None when embeddings are unavailable."""


@dataclass(frozen=True)
class VectorSearchResult:
    """A scored memory entry returned by vector search."""

    score: float
    entry: dict[str, Any]


class MemoryEmbeddingProvider:
    """Generate memory embeddings through the configured OpenAI-compatible LLM service."""

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        model: str | None = DEFAULT_MEMORY_EMBEDDING_MODEL,
        timeout: float = 30.0,
        client: OpenAI | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model = model or DEFAULT_MEMORY_EMBEDDING_MODEL
        self.timeout = timeout
        self._client = client
        self._available = bool(api_key or client)

    @classmethod
    def from_settings(cls, settings: Any) -> "MemoryEmbeddingProvider":
        return cls(
            api_key=getattr(settings, "api_key", None),
            base_url=getattr(settings, "base_url", ""),
            model=getattr(settings, "memory_embedding_model", DEFAULT_MEMORY_EMBEDDING_MODEL),
            timeout=getattr(settings, "dashscope_timeout_seconds", 30.0),
        )

    def embed(self, text: str) -> list[float] | None:
        clean = normalize_memory_text(text, 3000)
        if not clean or contains_sensitive_content(clean):
            return None
        if not self._available:
            return None

        try:
            response = self.client.embeddings.create(model=self.model, input=clean)
        except Exception:
            self._available = False
            return None

        data = getattr(response, "data", None)
        if not data:
            return None
        vector = getattr(data[0], "embedding", None)
        if not isinstance(vector, list) or not vector:
            return None

        try:
            return [float(value) for value in vector]
        except (TypeError, ValueError):
            return None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client


class LocalVectorStore:
    """Lightweight cosine-similarity vector search over JSON memory entries."""

    def search(
        self,
        entries: list[dict[str, Any]],
        query_embedding: list[float],
        *,
        limit: int,
    ) -> list[VectorSearchResult]:
        if not query_embedding or limit <= 0:
            return []

        scored: list[VectorSearchResult] = []
        for entry in entries:
            embedding = entry.get("embedding")
            if not isinstance(embedding, list):
                continue
            score = cosine_similarity(query_embedding, embedding)
            if score > 0:
                scored.append(VectorSearchResult(score=score, entry=entry))

        scored.sort(key=lambda item: (item.score, item.entry.get("created_at", "")), reverse=True)
        return scored[:limit]


def memory_embedding_text(question: str, answer: str) -> str:
    """Build the text sent to the embedding model for one memory entry."""

    return "\n".join(
        [
            f"question: {normalize_memory_text(question, 1000)}",
            f"answer: {normalize_memory_text(answer, 1800)}",
        ]
    )


def cosine_similarity(left: list[float], right: list[Any]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0

    try:
        right_values = [float(value) for value in right]
    except (TypeError, ValueError):
        return 0.0

    if np is not None:
        left_array = np.array(left, dtype=float)
        right_array = np.array(right_values, dtype=float)
        denominator = float(np.linalg.norm(left_array) * np.linalg.norm(right_array))
        if denominator == 0:
            return 0.0
        return float(np.dot(left_array, right_array) / denominator)

    dot = sum(a * b for a, b in zip(left, right_values, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right_values))
    denominator = left_norm * right_norm
    if denominator == 0:
        return 0.0
    return dot / denominator
