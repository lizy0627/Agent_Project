from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置，从环境变量或 .env 文件读取。"""

    # DashScope API Key：真实项目不要写死在代码里，避免泄露。
    dashscope_api_key: str

    # DashScope OpenAI 兼容模式地址。
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # 默认使用的通义千问模型名称。
    dashscope_model: str = "qwen-plus"

    # 让 pydantic-settings 自动读取 .env，并忽略未声明的变量。
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """缓存配置对象，避免每次请求都重新解析环境变量。"""

    return Settings()
