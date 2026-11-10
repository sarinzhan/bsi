"""The server tools over MCP: the server tools served by platform-api at /mcp/, called with this run's token.

A call can wait up to ~5 minutes while a person decides on the approval card, so reads wait longer.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any

import httpx2
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from agent_runner.interfaces import ToolResult, Tools, ToolSpec

CALL_TIMEOUT_S = 330  # platform-api gives up on an approval after 300 s


class McpTools(Tools):
    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def list(self) -> list[ToolSpec]:
        result = await self._session.list_tools()
        return [ToolSpec(t.name, t.description or "", t.input_schema) for t in result.tools]

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        result = await self._session.call_tool(name, arguments, read_timeout_seconds=CALL_TIMEOUT_S)
        text = "\n".join(getattr(c, "text", "") for c in getattr(result, "content", []) if getattr(c, "text", None))
        return ToolResult(text, bool(getattr(result, "is_error", False)))


@contextlib.asynccontextmanager
async def connect(url: str, run_token: str) -> AsyncIterator[McpTools]:
    timeout = httpx2.Timeout(30, read=CALL_TIMEOUT_S)
    async with httpx2.AsyncClient(headers={"Authorization": f"Bearer {run_token}"}, timeout=timeout) as http:
        async with streamable_http_client(url, http_client=http) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield McpTools(session)
