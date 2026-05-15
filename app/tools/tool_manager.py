from time import perf_counter
from typing import Any

from app.core.logger import get_logger
from app.tools.base import Tool, ToolResult


logger = get_logger(__name__)


class ToolManager:
    """Register and execute local tools with consistent logging and errors."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool
        logger.info("Tool registered: name=%s", tool.name)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def call(self, name: str, **kwargs: Any) -> ToolResult:
        started_at = perf_counter()
        tool = self.get(name)
        if tool is None:
            logger.warning("Tool call skipped because tool is not registered: name=%s", name)
            return ToolResult(
                name=name,
                success=False,
                error=f"Tool is not registered: {name}",
                duration_ms=self._elapsed_ms(started_at),
            )

        try:
            logger.info("Tool call started: name=%s args=%s", name, self._safe_log_args(kwargs))
            result = tool.run(**kwargs)
            logger.info("Tool call succeeded: name=%s", name)
            return ToolResult(
                name=name,
                success=True,
                result=result,
                duration_ms=self._elapsed_ms(started_at),
            )
        except Exception as exc:
            logger.exception("Tool call failed: name=%s", name)
            return ToolResult(
                name=name,
                success=False,
                error=str(exc),
                duration_ms=self._elapsed_ms(started_at),
            )

    def list_tools(self) -> list[str]:
        return sorted(self._tools)

    def _safe_log_args(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        safe_args: dict[str, Any] = {}
        for key, value in kwargs.items():
            if isinstance(value, str) and len(value) > 200:
                safe_args[key] = f"{value[:200]}..."
            else:
                safe_args[key] = value
        return safe_args

    def _elapsed_ms(self, started_at: float) -> float:
        return round((perf_counter() - started_at) * 1000, 2)
