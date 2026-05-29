import argparse
import json
from pathlib import Path
import sys
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.core.logger import get_logger, setup_logging


SERVERS_FILE = BASE_DIR / "app" / "mcp" / "servers.json"
logger = get_logger(__name__)


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Add or update an MCP server in app/mcp/servers.json.")
    parser.add_argument("--id", required=True, help="Server id, for example amap.")
    parser.add_argument("--name", required=True, help="Human-readable server name.")
    parser.add_argument("--url", required=True, help="Remote MCP endpoint URL.")
    parser.add_argument("--keywords", default="", help="Comma-separated keywords.")
    parser.add_argument("--description", default="", help="Server description.")
    parser.add_argument("--transport", default="http", choices=["http", "sse"], help="Transport type.")
    parser.add_argument("--category", default="", help="Optional category label.")
    parser.add_argument("--timeout-seconds", type=int, default=20, help="Per-server timeout.")
    parser.add_argument("--disabled", action="store_true", help="Add server as disabled.")
    args = parser.parse_args()

    servers = _read_servers()
    server_id = args.id.strip()
    servers[server_id] = {
        "name": args.name,
        "transport": args.transport,
        "url": args.url,
        "enabled": not args.disabled,
        "keywords": _split_keywords(args.keywords),
        "description": args.description,
        "timeout_seconds": args.timeout_seconds,
        "command": None,
        "args": [],
        "env": {},
        "headers": {},
        "category": args.category or None,
    }
    SERVERS_FILE.write_text(json.dumps(servers, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    logger.info("Added MCP server `%s` to %s", server_id, SERVERS_FILE)


def _read_servers() -> dict[str, Any]:
    if not SERVERS_FILE.exists():
        return {}
    data = json.loads(SERVERS_FILE.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"{SERVERS_FILE} must contain a JSON object.")
    return data


def _split_keywords(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


if __name__ == "__main__":
    main()
