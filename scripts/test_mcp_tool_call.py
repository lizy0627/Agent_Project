import argparse
import json
import sys
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.core.logger import setup_logging
from app.mcp.manager import MCPManager


def main() -> None:
    parser = argparse.ArgumentParser(description="Call one MCP tool with JSON arguments.")
    parser.add_argument("--server", required=True, help="Server id in app/mcp/servers.json.")
    parser.add_argument("--tool", required=True, help="Tool name exposed by the MCP server.")
    parser.add_argument("--arguments", default="{}", help="JSON object arguments.")
    args = parser.parse_args()

    setup_logging()
    arguments = _parse_arguments(args.arguments)
    manager = MCPManager()
    result = manager.call_tool(args.server, args.tool, arguments)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _parse_arguments(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        value = _parse_relaxed_object(raw)
        if value is None:
            raise SystemExit(f"--arguments must be a JSON object: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit("--arguments must be a JSON object.")
    return value


def _parse_relaxed_object(raw: str) -> dict[str, Any] | None:
    """Accept simple PowerShell-mangled input like {query:Qwen}."""

    text = raw.strip()
    if not (text.startswith("{") and text.endswith("}")):
        return None
    body = text[1:-1].strip()
    if not body:
        return {}

    parsed: dict[str, Any] = {}
    for pair in body.split(","):
        if ":" not in pair:
            return None
        key, value = pair.split(":", 1)
        parsed[key.strip().strip("'\"")] = value.strip().strip("'\"")
    return parsed


if __name__ == "__main__":
    main()
