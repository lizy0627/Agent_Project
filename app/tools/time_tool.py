from datetime import datetime
from zoneinfo import ZoneInfo

from app.tools.base import BaseTool


class CurrentTimeTool(BaseTool):
    """Return the current time for a requested timezone."""

    name = "get_current_time"
    description = "Get the current date and time."
    args_schema = {
        "type": "object",
        "properties": {
            "timezone": {
                "type": "string",
                "description": "IANA timezone name.",
                "default": "Asia/Shanghai",
            },
        },
    }

    def run(self, timezone: str = "Asia/Shanghai") -> dict[str, str]:
        try:
            tz = ZoneInfo(timezone)
        except Exception:
            timezone = "Asia/Shanghai"
            tz = ZoneInfo(timezone)

        now = datetime.now(tz)
        return {
            "timezone": timezone,
            "iso": now.isoformat(timespec="seconds"),
            "display": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
        }
