"""What the tools service offers: call a tool, list the tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from platform_api.tools.models import RunContext, ToolOutcome


@dataclass(frozen=True)
class ToolInfo:
    name: str
    kind: str
    summary: str
    params: str
    approval: str


class CallTool(Protocol):
    async def __call__(self, ctx: RunContext, tool: str, server: str, args: dict[str, Any]) -> ToolOutcome: ...


class ListTools(Protocol):
    def __call__(self) -> list[ToolInfo]: ...
