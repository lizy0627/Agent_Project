from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from app.core.logger import get_logger


logger = get_logger(__name__)
DEFAULT_SERVERS_FILE = Path(__file__).with_name("servers.json")


@dataclass(frozen=True)
class MCPServerConfig:
    """Configuration for one MCP server."""

    key: str
    name: str
    transport: str
    url: str
    enabled: bool = True
    description: str = ""


def load_server_configs(
    servers_file: Path | None = None,
    modelscope_url: str | None = None,
) -> dict[str, MCPServerConfig]:
    """Load MCP server definitions from servers.json."""

    config_file = servers_file or DEFAULT_SERVERS_FILE
    if not config_file.exists():
        logger.warning("MCP servers config file is missing: %s", config_file)
        return {}

    try:
        raw_configs = json.loads(config_file.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Failed to read MCP servers config: %s", config_file)
        return {}

    if not isinstance(raw_configs, dict):
        logger.warning("MCP servers config must be a JSON object: %s", config_file)
        return {}

    configs: dict[str, MCPServerConfig] = {}
    for key, raw_config in raw_configs.items():
        if not isinstance(raw_config, dict):
            logger.warning("Skip invalid MCP server config: key=%s", key)
            continue

        url = str(raw_config.get("url") or "").strip()
        if key == "modelscope" and modelscope_url:
            url = modelscope_url

        config = _build_server_config(key, raw_config, url)
        if config is None:
            continue

        configs[key] = config

    return configs


def _build_server_config(
    key: str,
    raw_config: dict[str, Any],
    url: str,
) -> MCPServerConfig | None:
    transport = str(raw_config.get("transport") or "http").strip().lower()
    if transport != "http":
        logger.warning(
            "Skip unsupported MCP server transport: key=%s transport=%s",
            key,
            transport,
        )
        return None

    if not url:
        logger.warning("Skip MCP server without url: key=%s", key)
        return None

    return MCPServerConfig(
        key=key,
        name=str(raw_config.get("name") or key),
        transport=transport,
        url=url,
        enabled=bool(raw_config.get("enabled", True)),
        description=str(raw_config.get("description") or ""),
    )
