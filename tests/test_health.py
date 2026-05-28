from importlib import import_module

from fastapi.testclient import TestClient

from app.core.config import get_settings


def test_health_check(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTO_OPEN_BROWSER", "false")
    monkeypatch.setenv("CONVERSATION_STORE", "memory")
    monkeypatch.setenv("AUTH_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setenv("DOCUMENT_DB_PATH", str(tmp_path / "documents.db"))
    get_settings.cache_clear()

    main = import_module("main")

    response = TestClient(main.app).get("/")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
