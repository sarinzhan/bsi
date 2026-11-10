"""Router: the MCP server the agent connects to (streamable HTTP at /mcp).

The agent's mcp config carries a per-run token:  Authorization: Bearer <run token>.
The token tells us which chat, system and environment the call belongs to; the agent cannot choose them.
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from platform_api.tools.models import RunContext
from platform_api.tools.schemas import CallTool
from platform_api.tools.interfaces import RunAuthority

INSTRUCTIONS = (
    "Tools to look at and change the servers of your system. Every call is shown to the developer for approval. "
    "Each server allows only the tools in its settings; other calls are rejected with the allowed list. "
    "Read tools: approved once per server per chat. Write tools and ssh_exec: approved every time, give a short reason. "
    "If a call is denied, do not repeat it. Paths are relative to /opt/bsi/<system>/<env>/."
)


def create_mcp_server(call: CallTool, authority: RunAuthority) -> MCPServer:
    mcp = MCPServer("bsi-server-tools", instructions=INSTRUCTIONS)

    async def run(ctx: Context, tool: str, server: str, **args: Any) -> str:
        auth = (ctx.headers or {}).get("authorization", "")
        token = auth.removeprefix("Bearer ").strip()
        run_ctx: RunContext | None = await authority.resolve(token) if token else None
        if run_ctx is None:
            raise ToolError("unauthorized: unknown or expired run token")
        outcome = await call(run_ctx, tool, server, {k: v for k, v in args.items() if v is not None})
        if outcome.status != "done":
            raise ToolError(outcome.text)  # marked as an error result for the agent
        return outcome.text

    # ---- read: approved once per server per chat ----

    @mcp.tool()
    async def folder_list(server: str, ctx: Context, path: str = ".") -> str:
        """List a folder inside the system folder."""
        return await run(ctx, "folder_list", server, path=path)

    @mcp.tool()
    async def file_read(server: str, path: str, ctx: Context, from_line: int = 1, lines: int = 200) -> str:
        """Read lines of a file in the system folder (.env files: variable names only, max 500 lines)."""
        return await run(ctx, "file_read", server, path=path, from_line=from_line, lines=lines)

    @mcp.tool()
    async def docker_ps(server: str, ctx: Context) -> str:
        """Containers of this system and environment, as JSON lines."""
        return await run(ctx, "docker_ps", server)

    @mcp.tool()
    async def docker_logs(server: str, service: str, ctx: Context, since: str = "1h", tail: int = 200) -> str:
        """Logs of a compose service. since like 30m/2h (max 24h), tail max 500."""
        return await run(ctx, "docker_logs", server, service=service, since=since, tail=tail)

    @mcp.tool()
    async def docker_inspect(server: str, service: str, ctx: Context) -> str:
        """Container details of a compose service, env values removed."""
        return await run(ctx, "docker_inspect", server, service=service)

    @mcp.tool()
    async def docker_stats(server: str, ctx: Context) -> str:
        """CPU and memory of this system's running containers."""
        return await run(ctx, "docker_stats", server)

    # ---- write: approved every time ----

    @mcp.tool()
    async def file_write(server: str, path: str, content: str, reason: str, ctx: Context) -> str:
        """Write a file in the system folder (keeps .bak). Commit the same change to git in this run."""
        return await run(ctx, "file_write", server, path=path, content=content, reason=reason)

    @mcp.tool()
    async def docker_run(server: str, image: str, reason: str, ctx: Context,
                         args: list[str] | None = None, env: dict[str, str] | None = None) -> str:
        """Run a one-off container (--rm) on the system network. Registry or allowlisted images, pinned tag."""
        return await run(ctx, "docker_run", server, image=image, reason=reason, args=args, env=env)

    @mcp.tool()
    async def compose_run(server: str, service: str, args: list[str], reason: str, ctx: Context) -> str:
        """Run a one-off command in a compose service, e.g. a DB migration."""
        return await run(ctx, "compose_run", server, service=service, args=args, reason=reason)

    @mcp.tool()
    async def compose_restart(server: str, service: str, reason: str, ctx: Context) -> str:
        """Restart a compose service."""
        return await run(ctx, "compose_restart", server, service=service, reason=reason)

    # ---- full access only ----

    @mcp.tool()
    async def ssh_exec(server: str, command: str, reason: str, ctx: Context, timeout_s: int = 60) -> str:
        """Any shell command, only where the server settings allow it. Use only when the tools above cannot answer."""
        return await run(ctx, "ssh_exec", server, command=command, reason=reason, timeout_s=timeout_s)

    return mcp
