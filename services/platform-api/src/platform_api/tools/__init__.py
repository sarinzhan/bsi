"""tools module: the server tools the agent calls (MCP)."""

from __future__ import annotations

from dataclasses import dataclass

from platform_api.tools.service import CallToolService
from platform_api.tools.service import ListToolsService
from platform_api.tools.catalog import ImagePolicy
from platform_api.tools.schemas import CallTool, ListTools
from platform_api.tools.interfaces import Approvals, AuditLog, Executor, Targets


@dataclass(frozen=True)
class ToolsModule:
    call_tool: CallTool
    list_tools: ListTools


def create_tools_module(targets: Targets, approvals: Approvals, executor: Executor, audit: AuditLog,
                        images: ImagePolicy = ImagePolicy()) -> ToolsModule:
    """Builds the module from what it needs and returns what it offers."""
    return ToolsModule(CallToolService(targets, approvals, executor, audit, images), ListToolsService())
