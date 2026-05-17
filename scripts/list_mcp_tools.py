import json
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.core.logger import setup_logging
from app.mcp.manager import MCPManager


def main() -> None:
    setup_logging()
    manager = MCPManager()
    print(json.dumps(manager.list_all_tools(), ensure_ascii=False, indent=2))
    errors = manager.get_tool_errors()
    if errors:
        print(json.dumps({"tool_discovery_errors": errors}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
