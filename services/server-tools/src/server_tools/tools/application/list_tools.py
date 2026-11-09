"""Use case: list the tools (for the Servers page and docs)."""

from __future__ import annotations

from server_tools.tools.domain.catalog import TOOLS
from server_tools.tools.domain.model import ToolKind
from server_tools.tools.ports.provided import ListTools, ToolInfo

APPROVAL = {
    ToolKind.READ: "once per server per chat · developer, devops or admin",
    ToolKind.WRITE: "every time, with a reason · devops or admin",
    ToolKind.FULL: "every time, exact command shown · devops or admin · never on prod",
}


class ListToolsService(ListTools):
    def __call__(self) -> list[ToolInfo]:
        return [ToolInfo(s.name, s.kind.value, s.summary, s.params, APPROVAL[s.kind]) for s in TOOLS.values()]
