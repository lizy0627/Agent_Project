import json
from typing import Any

from app.core.logger import get_logger
from app.core.safe_logging import safe_log_data, safe_log_field
from app.mcp.manager import MCPManager
from app.services.agent_planner import PlannedToolCall, normalize_query
from app.tools.base import ToolResult
from app.tools.tool_manager import MCP_SERVER_UNAVAILABLE, ToolManager


logger = get_logger(__name__)


class ToolExecutor:
    """Execute planned local and MCP tool calls through ToolManager."""

    def __init__(self, tool_manager: ToolManager, mcp_manager: MCPManager) -> None:
        self.tool_manager = tool_manager
        self.mcp_manager = mcp_manager

    def call_planned_tool(self, planned_call: PlannedToolCall | None) -> ToolResult | None:
            logger.info(
                "EXEC_TOOL=%s ARGS=%s",
                planned_call.name if planned_call else None,
                safe_log_data(planned_call.arguments) if planned_call else None,
            )
            if planned_call is None:
                logger.info("No tool call needed for current user message")
                return None

            logger.info(
                "Executing planned tool: name=%s arguments=%s",
                planned_call.name,
                safe_log_data(planned_call.arguments),
            )
            if planned_call.name == "mcp_tool":
                return self._call_mcp_tool(planned_call)

            tool_result = self.tool_manager.call(planned_call.name, **planned_call.arguments)
            return self._with_route_reason(tool_result, self._planned_route_reason(planned_call))
    def _log_planned_tool(self, planned_call: PlannedToolCall) -> None:
            logger.info(
                "PLANNED_TOOL=%s route_score=%s route_reason=%s ARGS=%s",
                planned_call.name,
                planned_call.route_score,
                planned_call.route_reason,
                safe_log_data(planned_call.arguments),
            )
    def _safe_planned_tool_log(self, planned_call: PlannedToolCall | None) -> dict[str, Any] | None:
            if planned_call is None:
                return None
            return {
                "name": planned_call.name,
                "arguments": safe_log_data(planned_call.arguments),
                "route_score": planned_call.route_score,
                "route_reason": planned_call.route_reason,
            }
    def _planned_route_reason(self, planned_call: PlannedToolCall) -> str:
            return planned_call.route_reason or str(planned_call.arguments.get("route_reason") or "")
    def _with_route_reason(self, tool_result: ToolResult, route_reason: str) -> ToolResult:
            if not route_reason or not isinstance(tool_result.result, dict):
                return tool_result

            result = dict(tool_result.result)
            result.setdefault("route_reason", route_reason)
            return ToolResult(
                name=tool_result.name,
                success=tool_result.success,
                result=result,
                error=tool_result.error,
                duration_ms=tool_result.duration_ms,
                error_code=tool_result.error_code,
                error_message=tool_result.error_message,
                retryable=tool_result.retryable,
            )
    def _call_mcp_tool(self, planned_call: PlannedToolCall) -> ToolResult:
            original_query = str(planned_call.arguments.get("original_query") or "")
            rewritten_query = str(planned_call.arguments.get("rewritten_query") or "")
            fallback_queries = planned_call.arguments.get("query_fallbacks")
            if not isinstance(fallback_queries, list) or not fallback_queries:
                fallback_queries = [rewritten_query or original_query]

            mcp_arguments = planned_call.arguments.get("arguments")
            base_mcp_arguments = mcp_arguments if isinstance(mcp_arguments, dict) else {}
            call_base = {
                key: value
                for key, value in planned_call.arguments.items()
                if key not in {
                    "arguments",
                    "original_query",
                    "rewritten_query",
                    "query_fallbacks",
                    "route_reason",
                }
            }

            last_result: ToolResult | None = None
            final_query = str(fallback_queries[0] or "")
            for index, query in enumerate(fallback_queries):
                query_text = str(query or "").strip()
                call_arguments = dict(call_base)
                call_arguments["arguments"] = self._with_mcp_query_arguments(base_mcp_arguments, query_text)
                last_result = self.tool_manager.call(planned_call.name, **call_arguments)
                last_result = self._normalize_mcp_tool_result(last_result)
                final_query = query_text

                if not self._is_empty_mcp_result(last_result):
                    break
                if index < len(fallback_queries) - 1:
                    logger.info(
                        "MCP result empty, fallback query: %s",
                        safe_log_field("query", fallback_queries[index + 1]),
                    )

            if last_result is None:
                fallback_call_arguments = {
                    key: value
                    for key, value in planned_call.arguments.items()
                    if key not in {"original_query", "rewritten_query", "query_fallbacks", "route_reason"}
                }
                last_result = self.tool_manager.call(planned_call.name, **fallback_call_arguments)
                last_result = self._normalize_mcp_tool_result(last_result)

            return self._with_mcp_query_metadata(
                last_result,
                original_query=original_query,
                rewritten_query=rewritten_query,
                final_query=final_query,
                route_reason=self._planned_route_reason(planned_call),
            )
    def _normalize_mcp_tool_result(self, tool_result: ToolResult) -> ToolResult:
            if tool_result.name != "mcp_tool" or not isinstance(tool_result.result, dict):
                return tool_result
            if tool_result.result.get("success") is not False:
                return tool_result

            return ToolResult(
                name=tool_result.name,
                success=False,
                result=tool_result.result,
                error=str(tool_result.result.get("error") or "MCP tool call failed."),
                duration_ms=tool_result.duration_ms,
                error_code=tool_result.error_code or MCP_SERVER_UNAVAILABLE,
                error_message=tool_result.error_message
                or str(tool_result.result.get("error") or "MCP tool call failed."),
                retryable=tool_result.retryable,
            )
    def _is_modelscope_mcp_call(self, planned_call: PlannedToolCall) -> bool:
            return (
                planned_call.name == "mcp_tool"
                and str(planned_call.arguments.get("server_name") or "").strip().lower() == "modelscope"
            )
    def _call_modelscope_mcp_tool(self, planned_call: PlannedToolCall) -> ToolResult:
            original_query = str(planned_call.arguments.get("original_query") or "")
            rewritten_query = str(planned_call.arguments.get("rewritten_query") or "")
            mcp_arguments = planned_call.arguments.get("arguments")
            base_mcp_arguments = mcp_arguments if isinstance(mcp_arguments, dict) else {}
            fallback_queries = self._modelscope_query_fallbacks(rewritten_query)
            if not fallback_queries:
                fallback_queries = [rewritten_query or original_query]

            logger.info("原问题: %s", safe_log_field("original_query", original_query))
            logger.info("重写后: %s", safe_log_field("rewritten_query", rewritten_query))

            last_result: ToolResult | None = None
            final_query = fallback_queries[0]
            for index, query in enumerate(fallback_queries):
                query_arguments = self._with_mcp_query_arguments(base_mcp_arguments, query)
                call_arguments = {
                    key: value
                    for key, value in planned_call.arguments.items()
                    if key not in {"arguments", "original_query", "rewritten_query", "route_reason"}
                }
                call_arguments["arguments"] = query_arguments
                last_result = self.tool_manager.call(planned_call.name, **call_arguments)
                final_query = query

                if not self._is_empty_modelscope_mcp_result(last_result):
                    break
                if index < len(fallback_queries) - 1:
                    logger.info(
                        "ModelScope MCP result empty, fallback query: %s",
                        safe_log_field("query", fallback_queries[index + 1]),
                    )

            logger.info("降级后: %s", safe_log_field("query", final_query))
            if last_result is not None:
                return self._with_modelscope_query_metadata(
                    last_result,
                    original_query=original_query,
                    rewritten_query=rewritten_query,
                    final_query=final_query,
                    route_reason=self._planned_route_reason(planned_call),
                )

            fallback_call_arguments = {
                key: value
                for key, value in planned_call.arguments.items()
                if key not in {"original_query", "rewritten_query", "route_reason"}
            }
            return self._with_route_reason(
                self.tool_manager.call(planned_call.name, **fallback_call_arguments),
                self._planned_route_reason(planned_call),
            )
    def _with_mcp_query_arguments(self, arguments: dict[str, Any], query: str) -> dict[str, Any]:
            updated = dict(arguments)
            url_keys = [
                key
                for key in updated
                if "url" in str(key).lower()
            ]
            if url_keys:
                for key in url_keys:
                    updated[key] = query
                return updated

            query_keys = [
                key
                for key in updated
                if self._looks_like_query_argument(str(key).lower())
            ]
            if not query_keys:
                updated["query"] = query
                return updated

            for key in query_keys:
                updated[key] = query
            return updated
    def _modelscope_query_fallbacks(self, query: str) -> list[str]:
            normalized = normalize_query(query)
            candidates = [normalized] if normalized else []
            if normalized.lower() == "qwen3":
                candidates.extend(["Qwen", "Qwen2"])
            return self._dedupe_nonempty(candidates)
    def _dedupe_nonempty(self, values: list[str]) -> list[str]:
            seen: set[str] = set()
            deduped: list[str] = []
            for value in values:
                cleaned = value.strip()
                if not cleaned:
                    continue
                key = cleaned.casefold()
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(cleaned)
            return deduped
    def _with_modelscope_query_metadata(
            self,
            tool_result: ToolResult,
            original_query: str,
            rewritten_query: str,
            final_query: str,
            route_reason: str,
        ) -> ToolResult:
            if isinstance(tool_result.result, dict):
                result = dict(tool_result.result)
                server_name = str(result.get("server_name") or "")
                server = self.mcp_manager.get_server(server_name) if server_name else None
                if server and server.url:
                    result["server_url"] = server.url
                result["query_rewrite"] = {
                    "original": original_query,
                    "rewritten": rewritten_query,
                    "final": final_query,
                }
                if route_reason:
                    result["route_reason"] = route_reason
            else:
                result = tool_result.result

            return ToolResult(
                name=tool_result.name,
                success=tool_result.success,
                result=result,
                error=tool_result.error,
                duration_ms=tool_result.duration_ms,
                error_code=tool_result.error_code,
                error_message=tool_result.error_message,
                retryable=tool_result.retryable,
            )
    def _with_mcp_query_metadata(
            self,
            tool_result: ToolResult,
            original_query: str,
            rewritten_query: str,
            final_query: str,
            route_reason: str,
        ) -> ToolResult:
            if isinstance(tool_result.result, dict):
                result = dict(tool_result.result)
                server_name = str(result.get("server_name") or "")
                server = self.mcp_manager.get_server(server_name) if server_name else None
                if server and server.url:
                    result["server_url"] = server.url
                result["query_rewrite"] = {
                    "original": original_query,
                    "rewritten": rewritten_query,
                    "final": final_query,
                }
                if route_reason:
                    result["route_reason"] = route_reason
            else:
                result = tool_result.result

            return ToolResult(
                name=tool_result.name,
                success=tool_result.success,
                result=result,
                error=tool_result.error,
                duration_ms=tool_result.duration_ms,
                error_code=tool_result.error_code,
                error_message=tool_result.error_message,
                retryable=tool_result.retryable,
            )
    def _is_empty_mcp_result(self, tool_result: ToolResult) -> bool:
            if not tool_result.success:
                return False
            if isinstance(tool_result.result, dict) and tool_result.result.get("success") is False:
                return False
            status = self._modelscope_collection_status(tool_result.result)
            return status is False
    def _is_empty_modelscope_mcp_result(self, tool_result: ToolResult) -> bool:
            if not tool_result.success:
                return False
            if isinstance(tool_result.result, dict) and tool_result.result.get("success") is False:
                return False

            status = self._modelscope_collection_status(tool_result.result)
            return status is False
    def _modelscope_collection_status(self, value: Any, from_collection_key: bool = False) -> bool | None:
            parsed_value = self._parse_json_if_possible(value)
            if parsed_value is not value:
                return self._modelscope_collection_status(parsed_value, from_collection_key=from_collection_key)

            if isinstance(value, dict):
                for key in ("result", "results", "models", "model_list", "items"):
                    if key in value:
                        status = self._modelscope_collection_status(value[key], from_collection_key=True)
                        if status is not None:
                            return status

                for key in ("structuredContent", "structured_content", "data", "content", "text"):
                    if key in value:
                        status = self._modelscope_collection_status(value[key])
                        if status is not None:
                            return status
                return None

            if isinstance(value, list):
                if not value:
                    return False

                child_statuses = [
                    self._modelscope_collection_status(item)
                    for item in value
                ]
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
