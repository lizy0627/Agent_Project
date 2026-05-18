import asyncio
from concurrent.futures import ThreadPoolExecutor
import inspect
from time import perf_counter
from typing import Any

import httpx

from app.core.logger import get_logger
from app.mcp.schema import MCPCallResult, MCPServerConfig


logger = get_logger(__name__)
MCP_SDK_NOT_INSTALLED_ERROR = "MCP Python SDK is not installed. Run `pip install -r requirements.txt`."


class MCPMissingSDKError(RuntimeError):
    """Raised only when importing the MCP Python SDK fails."""


class MCPClient:
    """Remote MCP client wrapper around the Python MCP SDK."""

    def __init__(
        self,
        servers: dict[str, MCPServerConfig] | None = None,
        timeout_seconds: int = 20,
    ) -> None:
        self.servers = servers or {}
        self.timeout_seconds = max(int(timeout_seconds), 1)

    def list_tools(self, server: MCPServerConfig | str) -> dict[str, Any]:
        config = self._resolve_server(server)
        server_name = config.key if config else str(server)
        return self._run_with_timeout(
            self._list_tools(config, server_name),
            server_name=server_name,
            url=str(config.url) if config else "",
            transport=str(config.transport) if config else "",
            tool_name="list_tools",
            arguments={},
            timeout_seconds=self._effective_timeout(config),
        )

    def call_tool(
        self,
        server: MCPServerConfig | str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        config = self._resolve_server(server)
        server_name = config.key if config else str(server)
        call_arguments = arguments or {}
        return self._run_with_timeout(
            self._call_tool(config, server_name, tool_name, call_arguments),
            server_name=server_name,
            url=str(config.url) if config else "",
            transport=str(config.transport) if config else "",
            tool_name=tool_name,
            arguments=call_arguments,
            timeout_seconds=self._effective_timeout(config),
        )

    async def _list_tools(
        self,
        config: MCPServerConfig | None,
        server_name: str,
    ) -> dict[str, Any]:
        started_at = perf_counter()
        if config is None:
            return self._failure(server_name, "list_tools", {}, "MCP server is not configured.", started_at)
        if not self._is_remote_transport_enabled(config):
            return self._failure(
                server_name,
                "list_tools",
                {},
                f"MCP server is disabled or unsupported: {server_name}",
                started_at,
            )

        try:
            logger.info(
                "MCP list_tools started: server_name=%s transport=%s url=%s",
                server_name,
                config.transport,
                config.url,
            )
            reachable_error = await self._check_server_reachable(config, tool_name="list_tools")
            if reachable_error:
                return self._failure(server_name, "list_tools", {}, reachable_error, started_at)

            async with self._open_session(config) as session:
                result = await session.list_tools()

            tools = [self._serialize_data(tool) for tool in getattr(result, "tools", [])]
            return self._success(server_name, "list_tools", {}, {"tools": tools}, started_at)
        except Exception as exc:
            logger.exception(
                "MCP list_tools failed: server_name=%s transport=%s url=%s tool_name=%s",
                server_name,
                config.transport,
                config.url,
                "list_tools",
            )
            return self._failure(server_name, "list_tools", {}, self._format_exception(exc), started_at)

    async def _call_tool(
        self,
        config: MCPServerConfig | None,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        started_at = perf_counter()
        if config is None:
            return self._failure(server_name, tool_name, arguments, "MCP server is not configured.", started_at)
        if not self._is_remote_transport_enabled(config):
            return self._failure(
                server_name,
                tool_name,
                arguments,
                f"MCP server is disabled or unsupported: {server_name}",
                started_at,
            )

        try:
            logger.info(
                "MCP call_tool started: server_name=%s transport=%s url=%s tool_name=%s arguments=%s",
                server_name,
                config.transport,
                config.url,
                tool_name,
                self._safe_log_args(arguments),
            )
            reachable_error = await self._check_server_reachable(config, tool_name=tool_name)
            if reachable_error:
                return self._failure(server_name, tool_name, arguments, reachable_error, started_at)

            async with self._open_session(config) as session:
                result = await session.call_tool(tool_name, arguments=arguments)

            return self._success(server_name, tool_name, arguments, self._serialize_data(result), started_at)
        except Exception as exc:
            logger.exception(
                "MCP call_tool failed: server_name=%s transport=%s url=%s tool_name=%s arguments=%s",
                server_name,
                config.transport,
                config.url,
                tool_name,
                self._safe_log_args(arguments),
            )
            return self._failure(server_name, tool_name, arguments, self._format_exception(exc), started_at)

    def _resolve_server(self, server: MCPServerConfig | str) -> MCPServerConfig | None:
        if isinstance(server, MCPServerConfig):
            return server
        config = self.servers.get(server)
        if config is None:
            logger.warning("MCP server is not configured: server_name=%s", server)
        return config

    def _is_remote_transport_enabled(self, config: MCPServerConfig) -> bool:
        if not config.enabled:
            logger.warning("MCP server is disabled: server_name=%s", config.key)
            return False
        if config.transport not in {"http", "sse"}:
            logger.warning(
                "MCP server transport is unsupported: server_name=%s transport=%s",
                config.key,
                config.transport,
            )
            return False
        if not config.url:
            logger.warning("MCP server url is empty: server_name=%s", config.key)
            return False
        return True

    def _run_with_timeout(
        self,
        coroutine: Any,
        server_name: str,
        url: str,
        transport: str,
        tool_name: str,
        arguments: dict[str, Any],
        timeout_seconds: int,
    ) -> dict[str, Any]:
        started_at = perf_counter()

        async def runner() -> dict[str, Any]:
            return await asyncio.wait_for(coroutine, timeout=timeout_seconds)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        try:
            if loop and loop.is_running():
                with ThreadPoolExecutor(max_workers=1) as executor:
                    return executor.submit(lambda: asyncio.run(runner())).result()
            return asyncio.run(runner())
        except (asyncio.TimeoutError, TimeoutError):
            error = f"MCP request timed out after {timeout_seconds}s."
            logger.exception(
                "MCP request timed out: server_name=%s transport=%s url=%s tool_name=%s arguments=%s",
                server_name,
                transport,
                url,
                tool_name,
                self._safe_log_args(arguments),
            )
            return self._failure(server_name, tool_name, arguments, error, started_at)
        except asyncio.CancelledError:
            logger.exception(
                "MCP request cancelled: server_name=%s transport=%s url=%s tool_name=%s arguments=%s",
                server_name,
                transport,
                url,
                tool_name,
                self._safe_log_args(arguments),
            )
            return self._failure(server_name, tool_name, arguments, "MCP request was cancelled.", started_at)
        except Exception as exc:
            logger.exception(
                "MCP request failed: server_name=%s transport=%s url=%s tool_name=%s arguments=%s",
                server_name,
                transport,
                url,
                tool_name,
                self._safe_log_args(arguments),
            )
            return self._failure(server_name, tool_name, arguments, self._format_exception(exc), started_at)

    def _open_session(self, config: MCPServerConfig) -> Any:
        return _RemoteMCPSession(
            transport=config.transport,
            url=str(config.url or ""),
            headers=config.headers,
            timeout_seconds=self._effective_timeout(config),
        )

    async def _check_server_reachable(self, config: MCPServerConfig, tool_name: str) -> str | None:
        try:
            method = "GET" if config.transport == "sse" else "HEAD"
            headers = {"Accept": "text/event-stream"} if config.transport == "sse" else None
            async with httpx.AsyncClient(
                timeout=self._effective_timeout(config),
                headers=config.headers or None,
            ) as client:
                async with client.stream(
                    method,
                    str(config.url),
                    headers=headers,
                ) as response:
                    response.raise_for_status()
        except httpx.ConnectError as exc:
            logger.exception(
                "MCP server is unreachable: server_name=%s transport=%s url=%s tool_name=%s",
                config.key,
                config.transport,
                config.url,
                tool_name,
            )
            return self._format_exception(exc)
        except httpx.TimeoutException as exc:
            logger.exception(
                "MCP server reachability check timed out: server_name=%s transport=%s url=%s tool_name=%s",
                config.key,
                config.transport,
                config.url,
                tool_name,
            )
            return self._format_exception(exc)
        except httpx.HTTPStatusError as exc:
            logger.exception(
                "MCP server returned HTTP status error: server_name=%s transport=%s url=%s tool_name=%s status_code=%s",
                config.key,
                config.transport,
                config.url,
                tool_name,
                exc.response.status_code,
            )
            return self._format_exception(exc)
        except Exception:
            logger.exception(
                "MCP reachability check returned non-fatal error: server_name=%s transport=%s url=%s tool_name=%s",
                config.key,
                config.transport,
                config.url,
                tool_name,
            )
        return None

    def _success(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
        data: Any,
        started_at: float,
    ) -> dict[str, Any]:
        elapsed_ms = self._elapsed_ms(started_at)
        logger.info(
            "MCP request succeeded: server_name=%s tool_name=%s elapsed_ms=%s",
            server_name,
            tool_name,
            elapsed_ms,
        )
        return MCPCallResult(
            success=True,
            server_name=server_name,
            tool_name=tool_name,
            arguments=arguments,
            data=data,
            elapsed_ms=elapsed_ms,
        ).model_dump(mode="json")

    def _failure(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
        error: str,
        started_at: float,
    ) -> dict[str, Any]:
        elapsed_ms = self._elapsed_ms(started_at)
        logger.warning(
            "MCP request failed: server_name=%s tool_name=%s arguments=%s elapsed_ms=%s error=%s",
            server_name,
            tool_name,
            self._safe_log_args(arguments),
            elapsed_ms,
            error,
        )
        return MCPCallResult(
            success=False,
            server_name=server_name,
            tool_name=tool_name,
            arguments=arguments,
            data=None,
            error=error,
            elapsed_ms=elapsed_ms,
        ).model_dump(mode="json")

    def _effective_timeout(self, config: MCPServerConfig | None) -> int:
        if config and config.timeout_seconds:
            return max(int(config.timeout_seconds), 1)
        return self.timeout_seconds

    def _elapsed_ms(self, started_at: float) -> float:
        return round((perf_counter() - started_at) * 1000, 2)

    def _serialize_data(self, data: Any) -> Any:
        if hasattr(data, "model_dump"):
            return data.model_dump(mode="json")
        if isinstance(data, dict):
            return {key: self._serialize_data(value) for key, value in data.items()}
        if isinstance(data, list | tuple):
            return [self._serialize_data(item) for item in data]
        return data

    def _safe_log_args(self, arguments: dict[str, Any]) -> dict[str, Any]:
        sensitive = ("token", "key", "secret", "authorization", "password")
        safe_args: dict[str, Any] = {}
        for key, value in arguments.items():
            lowered_key = str(key).lower()
            if any(marker in lowered_key for marker in sensitive):
                safe_args[key] = "***"
            elif isinstance(value, str) and len(value) > 200:
                safe_args[key] = f"{value[:200]}..."
            else:
                safe_args[key] = value
        return safe_args

    def _format_exception(self, exc: BaseException) -> str:
        if isinstance(exc, MCPMissingSDKError):
            return MCP_SDK_NOT_INSTALLED_ERROR

        if isinstance(exc, httpx.HTTPStatusError):
            request_url = exc.request.url if exc.request is not None else ""
            response_url = exc.response.url if exc.response is not None else request_url
            status_code = exc.response.status_code if exc.response is not None else "unknown"
            reason = exc.response.reason_phrase if exc.response is not None else ""
            return (
                f"HTTPStatusError: status_code={status_code} "
                f"url={response_url} reason={reason}".strip()
            )

        if isinstance(exc, BaseExceptionGroup):
            child_errors = "; ".join(self._format_exception(child) for child in exc.exceptions)
            return f"{exc.__class__.__name__}: {exc}; nested=[{child_errors}]"

        message = str(exc).strip()
        if message:
            return f"{exc.__class__.__name__}: {message}"
        return exc.__class__.__name__


class _RemoteMCPSession:
    """Async context manager that initializes one short-lived remote MCP session."""

    def __init__(
        self,
        transport: str,
        url: str,
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> None:
        self.transport = transport
        self.url = url
        self.headers = headers
        self.timeout_seconds = timeout_seconds
        self._http_client: httpx.AsyncClient | None = None
        self._client_context: Any = None
        self._session_context: Any = None

    async def __aenter__(self) -> Any:
        try:
            from mcp import ClientSession
            from mcp.client.sse import sse_client
            from mcp.client.streamable_http import streamablehttp_client
        except ImportError as exc:
            raise MCPMissingSDKError(MCP_SDK_NOT_INSTALLED_ERROR) from exc

        if self.transport == "http":
            self._client_context = self._create_streamable_http_context(streamablehttp_client)
        elif self.transport == "sse":
            self._client_context = self._create_sse_context(sse_client)
        else:
            raise ValueError(f"Unsupported MCP transport: {self.transport}")

        try:
            streams = await self._client_context.__aenter__()
            read_stream, write_stream = streams[0], streams[1]
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
        finally:
            if self._http_client is not None:
                await self._http_client.aclose()

    def _create_streamable_http_context(self, streamablehttp_client: Any) -> Any:
        parameters = inspect.signature(streamablehttp_client).parameters
        if "http_client" in parameters:
            self._http_client = httpx.AsyncClient(timeout=self.timeout_seconds, headers=self.headers or None)
            return streamablehttp_client(self.url, http_client=self._http_client)

        kwargs: dict[str, Any] = {}
        if "headers" in parameters:
            kwargs["headers"] = self.headers or None
        if "timeout" in parameters:
            kwargs["timeout"] = self.timeout_seconds
        return streamablehttp_client(self.url, **kwargs)

    def _create_sse_context(self, sse_client: Any) -> Any:
        parameters = inspect.signature(sse_client).parameters
        kwargs: dict[str, Any] = {}
        if "headers" in parameters:
            kwargs["headers"] = self.headers or None
        if "timeout" in parameters:
            kwargs["timeout"] = self.timeout_seconds
        return sse_client(self.url, **kwargs)
