from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ToolResult:
    """Normalized result returned by ToolManager."""

    name: str
    success: bool
    result: Any = None
    error: str | None = None
    duration_ms: float | None = None


class Tool(Protocol):
    """Protocol implemented by all local tools."""

    name: str
    description: str

    def run(self, **kwargs: Any) -> Any:
        """Execute the tool and return a JSON-serializable result."""
