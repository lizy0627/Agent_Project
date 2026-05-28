from importlib import import_module

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.services.conversation_store import create_conversation_store


def create_client(monkeypatch, tmp_path, auth_enabled: bool = True) -> TestClient:
    monkeypatch.setenv("AUTO_OPEN_BROWSER", "false")
    monkeypatch.setenv("AUTH_ENABLED", "true" if auth_enabled else "false")
    monkeypatch.setenv("AUTH_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setenv("AUTH_JWT_SECRET", "test-secret")
    monkeypatch.setenv("CONVERSATION_STORE", "sqlite")
    monkeypatch.setenv("CONVERSATION_DB_PATH", str(tmp_path / "conversations.db"))
    monkeypatch.setenv("DOCUMENT_DB_PATH", str(tmp_path / "documents.db"))
    get_settings.cache_clear()
    main = import_module("main")
    return TestClient(main.create_app())


def test_register_login_and_me(monkeypatch, tmp_path):
    client = create_client(monkeypatch, tmp_path)

    register_response = client.post(
        "/auth/register",
        json={"username": "alice", "password": "password123"},
    )

    assert register_response.status_code == 200
    token = register_response.json()["access_token"]

    login_response = client.post(
        "/auth/login",
        json={"username": "alice", "password": "password123"},
    )

    assert login_response.status_code == 200
    assert login_response.json()["access_token"]

    me_response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert me_response.status_code == 200
    assert me_response.json()["user"]["username"] == "alice"


def test_chat_requires_auth_when_enabled(monkeypatch, tmp_path):
    client = create_client(monkeypatch, tmp_path)

    response = client.post("/chat", json={"message": "hello"})

    assert response.status_code == 401
    assert response.json()["error_code"] == "AUTH_REQUIRED"


def test_auth_disabled_uses_dev_user(monkeypatch, tmp_path):
    client = create_client(monkeypatch, tmp_path, auth_enabled=False)

    response = client.get("/auth/me")

    assert response.status_code == 200
    assert response.json()["user"]["id"] == "__dev__"
    assert response.json()["user"]["auth_enabled"] is False


def test_conversations_are_scoped_by_user(tmp_path):
    store = create_conversation_store(
        store_type="sqlite",
        db_path=tmp_path / "conversations.db",
        max_rounds=10,
    )

    store.append_exchange("shared", "hello", "hi alice", user_id="1")

    assert store.get_messages("shared", user_id="1") == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi alice"},
    ]
    assert store.get_messages("shared", user_id="2") == []
