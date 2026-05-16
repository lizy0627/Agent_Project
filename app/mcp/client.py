import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any

import httpx

from app.core.logger import get_logger
from app.mcp.config import MCPServerConfig


logger = get_logger(__name__)


class MCPClient:
    """Thin Streamable HTTP client wrapper around the MCP Python SDK."""

    def __init__(
        self,
        servers: dict[str, MCPServerConfig],
        timeout_seconds: int = 20,
    ) -> None:
        self.servers = servers
        self.timeout_seconds = max(int(timeout_seconds), 1)

    def list_tools(self, server_name: str) -> dict[str, Any]:
        """Return tools exposed by one MCP server."""

        return self._run_with_timeout(
            self._list_tools(server_name),
            server_name=server_name,
            tool_name="list_tools",
        )

    def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call one tool on one MCP server."""

        return self._run_with_timeout(
            self._call_tool(server_name, tool_name, arguments or {}),
            server_name=server_name,
            tool_name=tool_name,
        )

    async def _list_tools(self, server_name: str) -> dict[str, Any]:
        config = self._get_enabled_server(server_name)
        if config is None:
            return self._failure(server_name, "list_tools", f"MCP server is not enabled: {server_name}")

        try:
            logger.info("MCP list_tools started: server=%s url=%s", server_name, config.url)
            reachable_error = await self._check_server_reachable(config)
            if reachable_error:
                return self._failure(server_name, "list_tools", reachable_error)

            async with self._open_session(config) as session:
                result = await session.list_tools()

            tools = [
                self._serialize_data(tool)
                for tool in getattr(result, "tools", [])
            ]
            logger.info("MCP list_tools succeeded: server=%s count=%s", server_name, len(tools))
            return self._success(server_name, "list_tools", {"tools": tools})
        except Exception as exc:
            logger.exception("MCP list_tools failed: server=%s", server_name)
            return self._failure(server_name, "list_tools", str(exc))

    async def _call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        config = self._get_enabled_server(server_name)
        if config is None:
            return self._failure(server_name, tool_name, f"MCP server is not enabled: {server_name}")

        try:
            logger.info(
                "MCP call_tool started: server=%s tool=%s args=%s",
                server_name,
                tool_name,
                self._safe_log_args(arguments),
            )
            reachable_error = await self._check_server_reachable(config)
            if reachable_error:
                return self._failure(server_name, tool_name, reachable_error)

            async with self._open_session(config) as session:
                result = await session.call_tool(tool_name, arguments=arguments)

            data = self._serialize_data(result)
            logger.info("MCP call_tool succeeded: server=%s tool=%s", server_name, tool_name)
            return self._success(server_name, tool_name, data)
        except Exception as exc:
            logger.exception("MCP call_tool failed: server=%s tool=%s", server_name, tool_name)
            return self._failure(server_name, tool_name, str(exc))

    def _get_enabled_server(self, server_name: str) -> MCPServerConfig | None:
        config = self.servers.get(server_name)
        if config is None:
            logger.warning("MCP server is not configured: server=%s", server_name)
            return None
        if not config.enabled:
            logger.warning("MCP server is disabled: server=%s", server_name)
            return None
        return config

    def _run_with_timeout(
        self,
        coroutine: Any,
        server_name: str,
        tool_name: str,
    ) -> dict[str, Any]:
        async def runner() -> dict[str, Any]:
            return await asyncio.wait_for(coroutine, timeout=self.timeout_seconds)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        try:
            if loop and loop.is_running():
                # Current FastAPI routes are sync, but scripts/tests may run inside a loop.
                with ThreadPoolExecutor(max_workers=1) as executor:
                    return executor.submit(lambda: asyncio.run(runner())).result()
            return asyncio.run(runner())
        except TimeoutError:
            logger.warning(
                "MCP request timed out: server=%s tool=%s timeout_seconds=%s",
                server_name,
                tool_name,
                self.timeout_seconds,
            )
            return self._failure(server_name, tool_name, "MCP request timed out.")
        except asyncio.CancelledError:
            logger.warning("MCP request was cancelled: server=%s tool=%s", server_name, tool_name)
            return self._failure(server_name, tool_name, "MCP request was cancelled.")
        except Exception as exc:
            logger.exception("MCP request failed: server=%s tool=%s", server_name, tool_name)
            return self._failure(server_name, tool_name, str(exc))

    def _open_session(self, config: MCPServerConfig) -> Any:
        return _StreamableHTTPSession(config.url, timeout_seconds=self.timeout_seconds)

    async def _check_server_reachable(self, config: MCPServerConfig) -> str | None:
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                # HEAD verifies that the HTTP endpoint is reachable without opening an SSE stream.
                await client.head(config.url)
        except httpx.ConnectError:
            logger.warning("MCP server is unreachable: server=%s url=%s", config.key, config.url)
            return (
                f"Cannot connect to MCP server `{config.key}` at {config.url}. "
                "Please check whether the MCP Server is running."
            )
        except httpx.TimeoutException:
            logger.warning("MCP server reachability check timed out: server=%s", config.key)
            return (
                f"MCP server `{config.key}` reachability check timed out. "
                "Please check the server address and network."
            )
        except Exception as exc:
            logger.info("MCP server reachability check returned non-fatal error: %s", exc)
        return None

    def _success(self, server_name: str, tool_name: str, data: Any) -> dict[str, Any]:
        return {
            "success": True,
            "server": server_name,
            "tool": tool_name,
            "data": data,
            "error": "",
        }

    def _failure(self, server_name: str, tool_name: str, error: str) -> dict[str, Any]:
        return {
            "success": False,
            "server": server_name,
            "tool": tool_name,
            "data": None,
            "error": error,
        }

    def _serialize_data(self, data: Any) -> Any:
        if hasattr(data, "model_dump"):
            return data.model_dump(mode="json")
        if isinstance(data, dict):
            return {key: self._serialize_data(value) for key, value in data.items()}
        if isinstance(data, list | tuple):
            return [self._serialize_data(item) for item in data]
        return data

    def _safe_log_args(self, arguments: dict[str, Any]) -> dict[str, Any]:
        safe_args: dict[str, Any] = {}
        for key, value in arguments.items():
            if isinstance(value, str) and len(value) > 200:
                safe_args[key] = f"{value[:200]}..."
            else:
                safe_args[key] = value
        return safe_args


class _StreamableHTTPSession:
    """Async context manager that initializes one short-lived MCP session."""

    def __init__(self, url: str, timeout_seconds: int) -> None:
        self.url = url
        self.timeout_seconds = timeout_seconds
        self._client_context: Any = None
        self._session_context: Any = None

    async def __aenter__(self) -> Any:
        try:
            from mcp import ClientSession
            try:
                from mcp.client.streamable_http import streamable_http_client as streamable_client
            except ImportError:
                from mcp.client.streamable_http import streamablehttp_client as streamable_client
        except ImportError as exc:
            raise RuntimeError(
                "MCP Python SDK is not installed. Run `pip install -r requirements.txt`."
            ) from exc

        timeout = timedelta(seconds=self.timeout_seconds)
        try:
            self._client_context = streamable_client(self.url, timeout=timeout)
        except TypeError as exc:
            if "timeout" not in str(exc):
                raise
            logger.info("MCP SDK streamable HTTP client does not accept timeout; using outer timeout")
            self._client_context = streamable_client(self.url)
        try:
            read_stream, write_stream, _get_session_id = await self._client_context.__aenter__()
            self._session_context = ClientSession(read_stream, write_stream)
            session = await self._session_context.__aenter__()
            await session.initialize()
            return session
        except BaseException:
            await self.__aexit__(None, None, None)
            raise

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        try:
            if self._session_context is not None:
                await self._session_context.__aexit__(exc_type, exc, traceback)
            if self._client_context is not None:
                await self._client_context.__aexit__(exc_type, exc, traceback)
        except Exception as close_error:
            logger.warning("MCP session close failed: %s", close_error)
