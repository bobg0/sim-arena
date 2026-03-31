"""
sim_mcp/client.py

Starts sim_mcp/server.py as a stdio subprocess and exposes:
  - anthropic_tools        : Anthropic-format tool definitions for the API call
  - call_tool(name, args)  : Execute a tool and return JSON string result

Use MCPClientSync (synchronous wrapper) in non-async code.

    with MCPClientSync() as client:
        tools  = client.anthropic_tools
        result = client.call_tool("get_pods", {"namespace": "virtual-default"})
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger("sim_mcp.client")

_SERVER_SCRIPT = str(Path(__file__).parent / "server.py")


def _mcp_tool_to_anthropic(tool) -> dict:
    return {
        "name":         tool.name,
        "description":  tool.description or "",
        "input_schema": tool.inputSchema if tool.inputSchema else {
            "type": "object", "properties": {},
        },
    }


async def _safe_close(client: "MCPClient") -> None:
    """
    Best-effort teardown of the MCP session and stdio subprocess.

    anyio raises RuntimeError('Attempted to exit cancel scope in a different
    task') when __aexit__ is called from a task that did not run __aenter__.
    We catch that specific error — the subprocess is killed by stdio_client's
    own cleanup regardless, so no resources are leaked.
    """
    try:
        if client._session is not None:
            await client._session.__aexit__(None, None, None)
    except (RuntimeError, Exception) as exc:
        logger.debug(f"MCP session close warning (safe to ignore): {exc}")

    try:
        if client._cm is not None:
            await client._cm.__aexit__(None, None, None)
    except (RuntimeError, Exception) as exc:
        logger.debug(f"MCP transport close warning (safe to ignore): {exc}")


class MCPClient:
    """Async MCP client. Use as an async context manager."""

    def __init__(self, server_script: str = _SERVER_SCRIPT) -> None:
        self._server_script   = server_script
        self._session: ClientSession | None = None
        self._cm              = None
        self._anthropic_tools: list[dict] | None = None

    async def __aenter__(self) -> "MCPClient":
        params = StdioServerParameters(
            command=sys.executable,
            args=[self._server_script],
        )
        self._cm = stdio_client(params)
        read, write = await self._cm.__aenter__()
        self._session = ClientSession(read, write)
        await self._session.__aenter__()
        await self._session.initialize()

        response = await self._session.list_tools()
        self._anthropic_tools = [_mcp_tool_to_anthropic(t) for t in response.tools]
        return self

    async def __aexit__(self, *args) -> None:
        await _safe_close(self)

    @property
    def anthropic_tools(self) -> list[dict]:
        if self._anthropic_tools is None:
            raise RuntimeError("MCPClient must be used as a context manager first.")
        return self._anthropic_tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        if self._session is None:
            raise RuntimeError("MCPClient is not connected.")
        result = await self._session.call_tool(name, arguments)
        parts = [b.text for b in result.content if hasattr(b, "text")]
        combined = "\n".join(parts)
        try:
            json.loads(combined)
            return combined
        except (json.JSONDecodeError, ValueError):
            return json.dumps({"result": combined})


class MCPClientSync:
    """
    Synchronous wrapper around MCPClient for use in non-async code.
    One instance per LLMAgent — not thread-safe.

        with MCPClientSync() as client:
            result = client.call_tool("get_pods", {"namespace": "x"})
    """

    def __init__(self, server_script: str = _SERVER_SCRIPT) -> None:
        self._server_script = server_script
        self._loop: asyncio.AbstractEventLoop | None = None
        self._async_client: MCPClient | None = None

    def __enter__(self) -> "MCPClientSync":
        self.start()
        return self

    def __exit__(self, *args) -> None:
        self.stop()

    def start(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._async_client = MCPClient(server_script=self._server_script)
        self._loop.run_until_complete(self._async_client.__aenter__())

    def stop(self) -> None:
        if self._loop and not self._loop.is_closed():
            try:
                if self._async_client is not None:
                    self._loop.run_until_complete(_safe_close(self._async_client))
            except Exception as exc:
                logger.debug(f"MCPClientSync.stop() cleanup warning: {exc}")
            finally:
                self._loop.close()
        self._async_client = None
        self._loop = None

    @property
    def anthropic_tools(self) -> list[dict]:
        if self._async_client is None:
            raise RuntimeError("MCPClientSync not started.")
        return self._async_client.anthropic_tools

    def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        if not self._loop or not self._async_client:
            raise RuntimeError("MCPClientSync not started.")
        return self._loop.run_until_complete(
            self._async_client.call_tool(name, arguments)
        )
