from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / "frontend"

APP_TITLE = "DashScope Minimal Agent"
APP_DESCRIPTION = "Minimal FastAPI agent example powered by DashScope."
APP_VERSION = "0.1.0"

HOST = "127.0.0.1"
PORT = 8000
FRONTEND_URL = f"http://{HOST}:{PORT}/ui"

DEFAULT_CORS_ALLOW_ORIGINS = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
]
CORS_ALLOW_ORIGINS = DEFAULT_CORS_ALLOW_ORIGINS


def _default_data_path(filename: str) -> Path:
    return BASE_DIR / "data" / filename


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env."""

    dashscope_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("API_KEY", "DASHSCOPE_API_KEY"),
    )
    dashscope_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        validation_alias=AliasChoices("BASE_URL", "DASHSCOPE_BASE_URL"),
    )
    dashscope_model: str = Field(
        default="qwen-plus",
        validation_alias=AliasChoices("MODEL_NAME", "DASHSCOPE_MODEL"),
    )
    tavily_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SEARCH_API_KEY", "TAVILY_API_KEY"),
    )
    memory_json_path: Path = Field(
        default_factory=lambda: _default_data_path("memories.json"),
        validation_alias=AliasChoices("MEMORY_PATH", "MEMORY_JSON_PATH"),
    )
    max_agent_steps: int = Field(
        default=8,
        ge=1,
        validation_alias=AliasChoices("MAX_AGENT_STEPS"),
    )

    dashscope_timeout_seconds: float = Field(
        default=30.0,
        validation_alias=AliasChoices("MODEL_TIMEOUT_SECONDS", "DASHSCOPE_TIMEOUT_SECONDS"),
    )
    web_search_provider: str = "tavily"
    web_search_timeout_seconds: float = Field(
        default=5.0,
        validation_alias=AliasChoices("WEB_SEARCH_TIMEOUT_SECONDS"),
    )
    web_reader_timeout_seconds: float = Field(
        default=5.0,
        validation_alias=AliasChoices("WEB_READER_TIMEOUT_SECONDS"),
    )
    search_workflow_read_top_k: int = Field(
        default=2,
        validation_alias=AliasChoices("SEARCH_WORKFLOW_READ_TOP_K", "WEB_SEARCH_READ_TOP_K"),
    )
    conversation_store: str = "memory"
    conversation_db_path: Path = _default_data_path("conversations.db")
    conversation_database_url: str | None = None
    conversation_max_rounds: int = Field(default=30, ge=1)
    memory_search_limit: int = 5
    memory_recent_context_limit: int = 6
    memory_vector_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("MEMORY_VECTOR_ENABLED"),
    )
    memory_vector_top_k: int = Field(
        default=5,
        ge=1,
        validation_alias=AliasChoices("MEMORY_VECTOR_TOP_K"),
    )
    memory_embedding_model: str = Field(
        default="text-embedding-v4",
        validation_alias=AliasChoices("MEMORY_EMBEDDING_MODEL"),
    )
    document_db_path: Path = _default_data_path("documents.db")
    document_upload_max_bytes: int = 5 * 1024 * 1024
    auth_enabled: bool = True
    auth_db_path: Path = _default_data_path("auth.db")
    auth_jwt_secret: str = "change-this-local-development-secret"
    auth_token_expire_minutes: int = 60 * 24
    auth_dev_user_id: str = "__dev__"
    auto_open_browser: bool = True
    mcp_enabled: bool = True
    mcp_default_server: str = "modelscope"
    modelscope_api_token: str | None = None
    modelscope_mcp_url: str = "http://127.0.0.1:8001/mcp"
    mcp_timeout_seconds: int = Field(
        default=20,
        validation_alias=AliasChoices("TOOL_TIMEOUT_SECONDS", "MCP_TIMEOUT_SECONDS"),
    )
    cors_allow_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: DEFAULT_CORS_ALLOW_ORIGINS.copy(),
    )

    @property
    def model_name(self) -> str:
        return self.dashscope_model

    @property
    def api_key(self) -> str | None:
        return self.dashscope_api_key

    @property
    def base_url(self) -> str:
        return self.dashscope_base_url

    @property
    def search_api_key(self) -> str | None:
        return self.tavily_api_key

    @property
    def memory_path(self) -> Path:
        return self.memory_json_path

    @field_validator("dashscope_api_key", "tavily_api_key", mode="before")
    @classmethod
    def empty_secret_as_missing(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator(
        "dashscope_model",
        "dashscope_base_url",
        "web_search_provider",
        "memory_embedding_model",
        mode="before",
    )
    @classmethod
    def non_empty_string(cls, value: Any, info):
        if isinstance(value, str) and not value.strip():
            env_name = {
                "dashscope_model": "MODEL_NAME",
                "dashscope_base_url": "BASE_URL",
                "web_search_provider": "WEB_SEARCH_PROVIDER",
                "memory_embedding_model": "MEMORY_EMBEDDING_MODEL",
            }.get(info.field_name, info.field_name)
            raise ValueError(f"{env_name} cannot be empty.")
        return value

    @field_validator("memory_json_path", mode="before")
    @classmethod
    def non_empty_memory_path(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            raise ValueError("MEMORY_PATH cannot be empty.")
        return value

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def parse_cors_allow_origins(cls, value):
        """Support comma-separated CORS origins in .env."""

        if value is None:
            return DEFAULT_CORS_ALLOW_ORIGINS.copy()
        if isinstance(value, str):
            origins = [origin.strip() for origin in value.split(",") if origin.strip()]
            return origins or DEFAULT_CORS_ALLOW_ORIGINS.copy()
        return value

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()
