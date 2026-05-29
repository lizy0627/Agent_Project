import json
import os
import re
from pathlib import Path
from typing import Any

from backend.app.core.config import BASE_DIR, get_settings
from backend.app.core.logger import get_logger
from backend.app.mcp.schema import MCPServerConfig


logger = get_logger(__name__)
DEFAULT_SERVERS_FILE = Path(__file__).with_name("servers.json")
ENV_PATTERN = re.compile(r"\$\{(?P<braced>[A-Za-z_][A-Za-z0-9_]*)\}|\$(?P<plain>[A-Za-z_][A-Za-z0-9_]*)")


def load_server_configs(
    servers_file: Path | None = None,
    modelscope_url: str | None = None,
) -> dict[str, MCPServerConfig]:
    """Load MCP server definitions from servers.json without connecting to them."""

    config_file = servers_file or DEFAULT_SERVERS_FILE
    if not config_file.exists():
        logger.warning("MCP servers config file is missing: %s", config_file)
        return {}

    try:
        raw_configs = json.loads(config_file.read_text(encoding="utf-8-sig"))
    except Exception:
        logger.exception("Failed to read MCP servers config: %s", config_file)
        return {}

    if not isinstance(raw_configs, dict):
        logger.warning("MCP servers config must be a JSON object: %s", config_file)
        return {}

    env_values = _load_env_values()
    settings = get_settings()
    resolved_modelscope_url = (
        modelscope_url
        or env_values.get("MODELSCOPE_MCP_URL")
        or settings.modelscope_mcp_url
    )

    configs: dict[str, MCPServerConfig] = {}
    for key, raw_config in raw_configs.items():
        if not isinstance(raw_config, dict):
            logger.warning("Skip invalid MCP server config: key=%s", key)
            continue

        expanded_config = _expand_env_values(raw_config, env_values)
        if key == "modelscope" and resolved_modelscope_url:
            expanded_config["url"] = resolved_modelscope_url

        try:
            config = MCPServerConfig(key=key, **expanded_config)
        except Exception:
            logger.exception("Skip invalid MCP server config: key=%s", key)
            continue

        if config.transport in {"http", "sse"} and not config.url:
            logger.warning(
                "Remote MCP server has no url configured: key=%s transport=%s",
                key,
                config.transport,
            )

        configs[key] = config

    return configs


def _load_env_values() -> dict[str, str]:
    """Read .env plus process environment; process env wins."""

    values: dict[str, str] = {}
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        try:
            for line in env_file.read_text(encoding="utf-8-sig").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                key, value = stripped.split("=", 1)
                values[key.strip()] = _unquote(value.strip())
        except Exception:
            logger.exception("Failed to read .env for MCP config expansion")

    values.update({key: value for key, value in os.environ.items()})
    return values


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _expand_env_values(value: Any, env_values: dict[str, str]) -> Any:
    if isinstance(value, str):
        return ENV_PATTERN.sub(
            lambda match: env_values.get(match.group("braced") or match.group("plain") or "", ""),
            value,
        )
    if isinstance(value, list):
        return [_expand_env_values(item, env_values) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _expand_env_values(item, env_values)
            for key, item in value.items()
        }
    return value
