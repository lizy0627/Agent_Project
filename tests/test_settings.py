from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config.settings import Settings
from app.core.errors import ApiKeyMissingError
from app.services.llm_client import LLMClient
from backend.app.config.settings import Settings as BackendSettings


def test_settings_loads_canonical_env_names(monkeypatch, tmp_path):
    memory_path = tmp_path / "memory.json"
    monkeypatch.setenv("MODEL_NAME", "qwen-turbo")
    monkeypatch.setenv("API_KEY", "model-key")
    monkeypatch.setenv("BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("SEARCH_API_KEY", "search-key")
    monkeypatch.setenv("MEMORY_PATH", str(memory_path))
    monkeypatch.setenv("MAX_AGENT_STEPS", "3")

    settings = Settings(_env_file=None)

    assert settings.model_name == "qwen-turbo"
    assert settings.api_key == "model-key"
    assert settings.base_url == "https://example.test/v1"
    assert settings.search_api_key == "search-key"
    assert settings.memory_path == Path(memory_path)
    assert settings.max_agent_steps == 3


def test_backend_settings_import_uses_same_settings_class():
    assert BackendSettings is Settings


def test_settings_rejects_empty_model_name(monkeypatch):
    monkeypatch.setenv("MODEL_NAME", " ")

    with pytest.raises(ValidationError, match="MODEL_NAME cannot be empty"):
        Settings(_env_file=None)


def test_llm_client_reports_missing_api_key():
    settings = Settings(_env_file=None).model_copy(update={"dashscope_api_key": None})

    with pytest.raises(ApiKeyMissingError, match="API_KEY is not configured"):
        LLMClient(settings)
