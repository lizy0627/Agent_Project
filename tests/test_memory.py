from app.api.chat import with_memory_context
from app.memory import MemoryManager


def test_memory_manager_saves_and_searches_long_memory(tmp_path):
    manager = MemoryManager(tmp_path / "memories.json")

    saved = manager.add_memory(
        user_id="alice",
        conversation_id="chat-1",
        question="请记住我喜欢用 FastAPI 构建后端服务",
        answer="好的，之后涉及后端方案时会优先考虑 FastAPI。",
    )

    assert saved is not None
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
