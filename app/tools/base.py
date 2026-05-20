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
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    data: Any = None

    def __post_init__(self) -> None:
        if self.data is None:
            object.__setattr__(self, "data", self.result)
        elif self.result is None:
            object.__setattr__(self, "result", self.data)


class Tool(Protocol):
    """Protocol implemented by all local tools."""

    name: str
    description: str

    def run(self, **kwargs: Any) -> Any:
        """Execute the tool and return a JSON-serializable result."""
