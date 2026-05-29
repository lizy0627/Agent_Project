import argparse
import json
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.core.logger import get_logger, setup_logging
from app.mcp.manager import MCPManager


logger = get_logger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Connect to one MCP server and print its tools.")
    parser.add_argument("--server", required=True, help="Server id in app/mcp/servers.json.")
    args = parser.parse_args()

    setup_logging()
    manager = MCPManager()
    server = manager.get_server(args.server)
    if server is None:
        logger.info(
            "%s",
            json.dumps({"success": False, "error": f"Server not found: {args.server}"}, ensure_ascii=False, indent=2),
        )
        return

    result = manager.client.list_tools(server)
    logger.info(
        "%s",
        json.dumps(
            {
                "server_name": server.key,
                "transport": server.transport,
                "url": server.url,
                "enabled": server.enabled,
                "result": result,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
