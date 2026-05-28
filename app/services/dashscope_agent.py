from app.services.agent_service import AgentService
from app.services.agent_types import AgentReply, AgentTraceStep, ChatMessage, SearchWorkflowPerformance, StatusCallback


class DashScopeAgent(AgentService):
    """Backward-compatible entry point for the FastAPI layer."""

    pass


__all__ = [
    "AgentReply",
    "AgentTraceStep",
    "ChatMessage",
    "DashScopeAgent",
    "SearchWorkflowPerformance",
    "StatusCallback",
]
