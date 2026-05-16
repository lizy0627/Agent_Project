import json
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.core.config import get_settings
from app.core.logger import setup_logging
from app.mcp.manager import MCPManager


def main() -> None:
    setup_logging()
    settings = get_settings()
    manager = MCPManager(
        timeout_seconds=settings.mcp_timeout_seconds,
        modelscope_url=settings.modelscope_mcp_url,
    )
    result = manager.client.list_tools("modelscope")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
