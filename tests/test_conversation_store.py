import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.api import chat as chat_api
from app.api.auth import CurrentUser
from app.services.conversation_store import SQLAlchemyConversationStore, create_conversation_store


def test_sqlalchemy_store_creates_and_lists_user_conversations(tmp_path):
    store = create_conversation_store(
        store_type="sqlite",
        db_path=tmp_path / "conversations.db",
        max_rounds=10,
    )

    store.append_exchange("shared", "hello alice", "hi alice", user_id="alice")
    store.append_exchange("shared", "hello bob", "hi bob", user_id="bob")

    alice_page = store.list_conversations(user_id="alice", limit=10, offset=0)
    bob_page = store.list_conversations(user_id="bob", limit=10, offset=0)

    assert alice_page.total == 1
    assert alice_page.conversations[0].id == "shared"
    assert alice_page.conversations[0].title == "hello alice"
    assert alice_page.conversations[0].message_count == 2
    assert bob_page.total == 1
    assert bob_page.conversations[0].title == "hello bob"
    assert store.get_messages("shared", user_id="alice") == [
        {"role": "user", "content": "hello alice"},
        {"role": "assistant", "content": "hi alice"},
    ]


def test_sqlalchemy_store_appends_clears_and_paginates_messages(tmp_path):
    store = create_conversation_store(
        store_type="sqlite",
        db_path=tmp_path / "conversations.db",
        max_rounds=10,
    )

    for index in range(5):
        store.append_message("paged", "user", f"message {index}", user_id="alice")

    page = store.get_message_page("paged", user_id="alice", limit=2, offset=1)

    assert page.total == 5
    assert page.limit == 2
    assert page.offset == 1
    assert page.has_more is True
    assert page.messages == [
        {"role": "user", "content": "message 1"},
        {"role": "user", "content": "message 2"},
    ]

    store.clear("paged", user_id="alice")

    assert store.get_messages("paged", user_id="alice") == []
    assert store.list_conversations(user_id="alice").total == 0


def test_get_messages_returns_recent_window_without_loading_full_history(tmp_path):
    store = create_conversation_store(
        store_type="sqlite",
        db_path=tmp_path / "conversations.db",
        max_rounds=2,
    )

    for index in range(6):
        store.append_message("recent", "user", f"message {index}", user_id="alice")

    assert store.get_messages("recent", user_id="alice") == [
        {"role": "user", "content": "message 2"},
        {"role": "user", "content": "message 3"},
        {"role": "user", "content": "message 4"},
        {"role": "user", "content": "message 5"},
    ]
    assert store.get_message_page("recent", user_id="alice", limit=10, offset=0).total == 4


def test_sqlalchemy_schema_contains_production_tables(tmp_path):
    store = SQLAlchemyConversationStore(db_path=tmp_path / "conversations.db")

    table_names = set(inspect(store.engine).get_table_names())

    assert {
        "users",
        "conversations",
        "messages",
        "documents",
        "tool_call_logs",
        "agent_traces",
    }.issubset(table_names)


def test_legacy_sqlite_messages_are_migrated_to_new_schema(tmp_path):
    db_path = tmp_path / "conversations.db"
    connection = sqlite3.connect(db_path)
    with connection:
        connection.execute(
            """
            CREATE TABLE conversation_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL DEFAULT '__dev__',
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            INSERT INTO conversation_messages (user_id, conversation_id, role, content)
            VALUES ('alice', 'legacy', 'user', 'hello')
            """
        )
    connection.close()

    store = create_conversation_store(store_type="sqlite", db_path=db_path, max_rounds=10)

    assert store.get_messages("legacy", user_id="alice") == [{"role": "user", "content": "hello"}]
    assert store.list_conversations(user_id="alice").total == 1


def test_conversation_api_uses_paginated_store_results():
    store = create_conversation_store(store_type="memory", max_rounds=10)
    for index in range(3):
        store.append_message("api", "user", f"message {index}", user_id="alice")

    app = FastAPI()
    app.include_router(chat_api.router)
    app.dependency_overrides[chat_api.get_current_user] = lambda: CurrentUser(user_id="alice", username="alice")
    app.dependency_overrides[chat_api.get_conversation_store] = lambda: store
    client = TestClient(app)

    conversations_response = client.get("/conversations?limit=1&offset=0")
    messages_response = client.get("/conversations/api/messages?limit=2&offset=1")

    assert conversations_response.status_code == 200
    assert conversations_response.json()["total"] == 1
    assert conversations_response.json()["conversations"][0]["id"] == "api"
    assert messages_response.status_code == 200
    assert messages_response.json()["total"] == 3
    assert messages_response.json()["messages"] == [
        {"role": "user", "content": "message 1"},
        {"role": "user", "content": "message 2"},
    ]
