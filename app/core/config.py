from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / "frontend"

APP_TITLE = "DashScope Minimal Agent"
APP_DESCRIPTION = "Minimal FastAPI agent example powered by DashScope."
APP_VERSION = "0.1.0"

HOST = "127.0.0.1"
PORT = 8000
FRONTEND_URL = f"http://{HOST}:{PORT}/ui"

CORS_ALLOW_ORIGINS = ["*"]


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env."""

    dashscope_api_key: str | None = None
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_model: str = "qwen-plus"
    dashscope_timeout_seconds: float = 30.0
    tavily_api_key: str | None = None
    web_search_provider: str = "tavily"
    mcp_enabled: bool = True
    mcp_default_server: str = "modelscope"
    modelscope_api_token: str | None = None
    modelscope_mcp_url: str = "http://127.0.0.1:8001/mcp"
    mcp_timeout_seconds: int = 20

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()
