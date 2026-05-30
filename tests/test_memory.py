import json

from app.api.chat import with_memory_context
from app.memory import MemoryManager


class FakeEmbeddingProvider:
    def __init__(self, vectors):
        self.vectors = vectors

    def embed(self, text: str):
        for key, vector in self.vectors.items():
            if key in text:
                return vector
        return None


def test_memory_manager_saves_and_searches_long_memory(tmp_path):
    manager = MemoryManager(tmp_path / "memories.json")

    saved = manager.add_memory(
        user_id="alice",
        conversation_id="chat-1",
        question="请记住我喜欢用 FastAPI 构建后端服务",
        answer="好的，之后涉及后端方案时会优先考虑 FastAPI。",
    )

    assert saved is not None
    assert "embedding" in saved
    results = manager.search_memory(user_id="alice", query="FastAPI 后端怎么设计")
    assert len(results) == 1
    assert "FastAPI" in results[0]["question"]


def test_memory_manager_returns_recent_short_context(tmp_path):
    manager = MemoryManager(tmp_path / "memories.json", short_limit=4)

    manager.add_memory(user_id="alice", conversation_id="chat-1", question="第一轮问题", answer="第一轮回答")
    manager.add_memory(user_id="alice", conversation_id="chat-1", question="第二轮问题", answer="第二轮回答")

    context = manager.get_recent_context(user_id="alice", conversation_id="chat-1", limit=3)

    assert context == [
        {"role": "assistant", "content": "第一轮回答"},
        {"role": "user", "content": "第二轮问题"},
        {"role": "assistant", "content": "第二轮回答"},
    ]


def test_memory_manager_does_not_store_sensitive_content(tmp_path):
    manager = MemoryManager(tmp_path / "memories.json")

    saved = manager.add_memory(
        user_id="alice",
        conversation_id="chat-1",
        question="我的 API_KEY=secret-value，请帮我记住",
        answer="好的",
    )

    assert saved is None
    assert manager.search_memory(user_id="alice", query="secret") == []
    assert manager.get_recent_context(user_id="alice", conversation_id="chat-1") == []


def test_memory_context_is_inserted_after_system_prompt():
    messages = [
        {"role": "system", "content": "base"},
        {"role": "user", "content": "hello"},
    ]
    memory_messages = [{"role": "system", "content": "memory"}]

    assert with_memory_context(messages, memory_messages) == [
        {"role": "system", "content": "base"},
        {"role": "system", "content": "memory"},
        {"role": "user", "content": "hello"},
    ]


def test_memory_manager_prefers_vector_search_when_available(tmp_path):
    manager = MemoryManager(
        tmp_path / "memories.json",
        vector_enabled=True,
        vector_top_k=1,
        embedding_provider=FakeEmbeddingProvider(
            {
                "FastAPI": [1.0, 0.0],
                "Postgres": [0.0, 1.0],
                "database retrieval": [0.0, 1.0],
            }
        ),
    )

    manager.add_memory(
        user_id="alice",
        conversation_id="chat-1",
        question="Use FastAPI for backend services",
        answer="Prefer FastAPI for HTTP APIs.",
    )
    manager.add_memory(
        user_id="alice",
        conversation_id="chat-1",
        question="Use Postgres for durable storage",
        answer="Prefer Postgres for relational data.",
    )

    results = manager.search_memory(user_id="alice", query="database retrieval", limit=2)

    assert len(results) == 1
    assert results[0]["question"] == "Use Postgres for durable storage"
    assert results[0]["score_type"] == "vector"
    assert results[0]["embedding"] == [0.0, 1.0]


def test_memory_manager_falls_back_to_text_search_when_embedding_unavailable(tmp_path):
    manager = MemoryManager(
        tmp_path / "memories.json",
        vector_enabled=True,
        embedding_provider=FakeEmbeddingProvider({}),
    )

    manager.add_memory(
        user_id="alice",
        conversation_id="chat-1",
        question="Remember FastAPI backend preference",
        answer="FastAPI should be preferred for backend API work.",
    )

    results = manager.search_memory(user_id="alice", query="FastAPI backend")

    assert len(results) == 1
    assert results[0]["question"] == "Remember FastAPI backend preference"
    assert "score_type" not in results[0]


def test_memory_manager_reads_old_json_memory_without_embeddings(tmp_path):
    memory_path = tmp_path / "memories.json"
    memory_path.write_text(
        json.dumps(
            {
                "short": {},
                "long": {
                    "alice": [
                        {
                            "id": "old-1",
                            "user_id": "alice",
                            "conversation_id": "chat-1",
                            "question": "Old FastAPI memory",
                            "answer": "Use FastAPI for API services.",
                            "keywords": ["old", "fastapi", "memory"],
                            "created_at": "2026-01-01T00:00:00+00:00",
                        }
                    ]
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    manager = MemoryManager(
        memory_path,
        vector_enabled=True,
        embedding_provider=FakeEmbeddingProvider({"FastAPI": [1.0, 0.0]}),
    )

    results = manager.search_memory(user_id="alice", query="FastAPI")

    assert len(results) == 1
    assert results[0]["id"] == "old-1"
