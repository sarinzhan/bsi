"""tools module: the server tools the agent calls (MCP)."""

from __future__ import annotations

from dataclasses import dataclass

from server_tools.tools.application.call_tool import CallToolService
from server_tools.tools.application.list_tools import ListToolsService
from server_tools.tools.domain.catalog import ImagePolicy
from server_tools.tools.ports.provided import CallTool, ListTools
from server_tools.tools.ports.required import Approvals, AuditLog, Executor, Targets


@dataclass(frozen=True)
class ToolsModule:
    call_tool: CallTool
    list_tools: ListTools


def create_tools_module(targets: Targets, approvals: Approvals, executor: Executor, audit: AuditLog,
                        images: ImagePolicy = ImagePolicy()) -> ToolsModule:
    """Wires the module from its required ports and returns its provided ports."""
    return ToolsModule(CallToolService(targets, approvals, executor, audit, images), ListToolsService())
