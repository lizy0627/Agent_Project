from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


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


class BaseTool(ABC):
    """Base class for all tools registered in ToolRegistry."""

    name: str = ""
    description: str = ""
    args_schema: dict[str, Any] = {}

    @abstractmethod
    def run(self, **kwargs: Any) -> Any:
        """Execute the tool and return a JSON-serializable result."""

    def definition(self) -> dict[str, Any]:
        """Return the tool metadata exposed by the registry."""

        return {
            "name": self.name,
            "description": self.description,
            "args_schema": self.args_schema,
        }
