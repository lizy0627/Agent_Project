import json
from typing import Any

from backend.app.core.config import get_settings
from backend.app.core.logger import get_logger
from backend.app.core.safe_logging import safe_log_field
from backend.app.mcp.manager import MCPManager
from backend.app.mcp.schema import MCPCallResult
from backend.app.tools.base import BaseTool


logger = get_logger(__name__)


class MCPTool(BaseTool):
    """Expose MCP servers as one ordinary registry tool."""

    name = "mcp_tool"
    description = "Call a tool from a configured MCP server."
    args_schema = {
        "type": "object",
        "properties": {
            "server_name": {
                "type": "string",
                "description": "Configured MCP server name.",
            },
            "tool_name": {
                "type": "string",
                "description": "Tool name exposed by the MCP server.",
            },
            "arguments": {
                "type": "object",
                "description": "Arguments passed to the MCP tool.",
                "default": {},
            },
            "original_query": {
                "type": "string",
                "description": "Original user query, used only for trace metadata.",
                "default": "",
            },
            "rewritten_query": {
                "type": "string",
                "description": "Planner rewritten query, used for fallback calls.",
                "default": "",
            },
            "query_fallbacks": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Fallback query strings to try when an MCP search result is empty.",
                "default": [],
            },
            "route_reason": {
                "type": "string",
                "description": "Planner route reason, used only for trace metadata.",
                "default": "",
            },
        },
        "required": ["server_name", "tool_name"],
    }

    def __init__(self, manager: MCPManager | None = None) -> None:
        self.manager = manager

    def run(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        original_query: str = "",
        rewritten_query: str = "",
        query_fallbacks: list[str] | None = None,
        route_reason: str = "",
    ) -> dict[str, Any]:
        settings = get_settings()
        if not settings.mcp_enabled:
            return MCPCallResult(
                success=False,
                server_name=server_name,
                tool_name=tool_name,
                arguments=arguments or {},
                data=None,
                error="MCP is disabled by configuration.",
            ).model_dump(mode="json")

        try:
            if self.manager is None:
                self.manager = MCPManager()
            return self._run_with_fallbacks(
                server_name=server_name,
                tool_name=tool_name,
                arguments=arguments or {},
                original_query=original_query,
                rewritten_query=rewritten_query,
                query_fallbacks=query_fallbacks,
                route_reason=route_reason,
            )
        except Exception as exc:
            logger.exception("MCP tool wrapper failed: server=%s tool=%s", server_name, tool_name)
            return MCPCallResult(
                success=False,
                server_name=server_name,
                tool_name=tool_name,
                arguments=arguments or {},
                data=None,
                error=str(exc),
            ).model_dump(mode="json")

    def _run_with_fallbacks(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
        original_query: str,
        rewritten_query: str,
        query_fallbacks: list[str] | None,
        route_reason: str,
    ) -> dict[str, Any]:
        fallback_queries = query_fallbacks if isinstance(query_fallbacks, list) else []
        if not fallback_queries:
            fallback_queries = [rewritten_query or original_query]
        fallback_queries = self._dedupe_nonempty(fallback_queries)

        if not fallback_queries:
            result = self._call_manager(server_name, tool_name, arguments)
            return self._with_query_metadata(
                result,
                server_name=server_name,
                original_query=original_query,
                rewritten_query=rewritten_query,
                final_query="",
                route_reason=route_reason,
            )

        last_result: dict[str, Any] | None = None
        final_query = fallback_queries[0]
        for index, query in enumerate(fallback_queries):
            query_text = str(query or "").strip()
            call_arguments = self._with_mcp_query_arguments(arguments, query_text)
            last_result = self._call_manager(server_name, tool_name, call_arguments)
            final_query = query_text

            if not self._is_empty_mcp_result(last_result):
                break
            if index < len(fallback_queries) - 1:
                logger.info(
                    "MCP result empty, fallback query: %s",
                    safe_log_field("query", fallback_queries[index + 1]),
                )

        result = last_result or self._call_manager(server_name, tool_name, arguments)
        return self._with_query_metadata(
            result,
            server_name=server_name,
            original_query=original_query,
            rewritten_query=rewritten_query,
            final_query=final_query,
            route_reason=route_reason,
        )

    def _call_manager(self, server_name: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.manager is None:
            self.manager = MCPManager()
        result = self.manager.call_tool(server_name, tool_name, arguments)
        if not result.get("success") and not result.get("error"):
            result["error"] = "MCP tool call failed. Please check whether the MCP Server is running."
        return result

    def _with_mcp_query_arguments(self, arguments: dict[str, Any], query: str) -> dict[str, Any]:
        updated = dict(arguments)
        url_keys = [key for key in updated if "url" in str(key).lower()]
        if url_keys:
            for key in url_keys:
                updated[key] = query
            return updated

        query_keys = [key for key in updated if self._looks_like_query_argument(str(key).lower())]
        if not query_keys:
            updated["query"] = query
            return updated

        for key in query_keys:
            updated[key] = query
        return updated

    def _with_query_metadata(
        self,
        result: dict[str, Any],
        server_name: str,
        original_query: str,
        rewritten_query: str,
        final_query: str,
        route_reason: str,
    ) -> dict[str, Any]:
        enriched = dict(result)
        server = self.manager.get_server(server_name) if self.manager is not None else None
        if server and server.url:
            enriched["server_url"] = server.url
        if original_query or rewritten_query or final_query:
            enriched["query_rewrite"] = {
                "original": original_query,
                "rewritten": rewritten_query,
                "final": final_query,
            }
        if route_reason:
            enriched["route_reason"] = route_reason
        return enriched

    def _is_empty_mcp_result(self, result: dict[str, Any]) -> bool:
        if not result.get("success"):
            return False
        return self._collection_status(result) is False

    def _collection_status(self, value: Any, from_collection_key: bool = False) -> bool | None:
        parsed_value = self._parse_json_if_possible(value)
        if parsed_value is not value:
            return self._collection_status(parsed_value, from_collection_key=from_collection_key)

        if isinstance(value, dict):
            for key in ("result", "results", "models", "model_list", "items"):
                if key in value:
                    status = self._collection_status(value[key], from_collection_key=True)
                    if status is not None:
                        return status

            for key in ("structuredContent", "structured_content", "data", "content", "text"):
                if key in value:
                    status = self._collection_status(value[key])
                    if status is not None:
                        return status
            return None

        if isinstance(value, list):
            if not value:
                return False

            child_statuses = [self._collection_status(item) for item in value]
            if any(status is True for status in child_statuses):
                return True
            if any(status is False for status in child_statuses):
                return False
            return True if from_collection_key else None

        return None

    def _parse_json_if_possible(self, value: Any) -> Any:
        if not isinstance(value, str):
            return value

        stripped = value.strip()
        if not stripped or stripped[0] not in "[{":
            return value

        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return value

    def _looks_like_query_argument(self, name: str) -> bool:
        query_keywords = ("query", "keyword", "keywords", "search", "q", "text", "name")
        return any(keyword in name for keyword in query_keywords)

    def _dedupe_nonempty(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for value in values:
            cleaned = str(value or "").strip()
            if not cleaned:
                continue
            key = cleaned.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(cleaned)
        return deduped
