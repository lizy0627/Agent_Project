from functools import lru_cache
from pathlib import Path
from typing import Annotated

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


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env."""

    dashscope_api_key: str | None = None
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_model: str = "qwen-plus"
    dashscope_timeout_seconds: float = Field(
        default=30.0,
        validation_alias=AliasChoices("MODEL_TIMEOUT_SECONDS", "DASHSCOPE_TIMEOUT_SECONDS"),
    )
    tavily_api_key: str | None = None
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
    conversation_db_path: Path = BASE_DIR / "data" / "conversations.db"
    conversation_database_url: str | None = None
    document_db_path: Path = BASE_DIR / "data" / "documents.db"
    document_upload_max_bytes: int = 5 * 1024 * 1024
    auth_enabled: bool = True
    auth_db_path: Path = BASE_DIR / "data" / "auth.db"
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
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()
