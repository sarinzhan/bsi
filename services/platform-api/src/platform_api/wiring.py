"""Glue between modules that must not know each other. Lives outside them, like main.py.

- agent tells "a run ended" through its RunListener port; chat shows it.
- servers asks which tools exist through its KnownTools port; the tools module's catalog answers.
"""

from __future__ import annotations

from dataclasses import asdict

from platform_api.agent.schemas import RunInfo
from platform_api.agent.interfaces import RunListener
from platform_api.chat.schemas import RunnerChat
from platform_api.servers.interfaces import KnownTools, ToolCatalogUnavailable
from platform_api.tools.schemas import ListTools


class ChatRunListener(RunListener):
    def __init__(self) -> None:
        self.chat: RunnerChat | None = None  # set after the chat module exists (it needs agent first)

    def ended(self, run: RunInfo) -> None:
        if self.chat is not None:
            self.chat.run_ended(run.chat_id, run.run_id, run.status, run.error)


class ToolCatalog(KnownTools):
    def __init__(self) -> None:
        self.list_tools: ListTools | None = None  # set after the tools module exists (it needs servers first)

    def _tools(self) -> list:
        if self.list_tools is None:
            raise ToolCatalogUnavailable("the tools module is not ready")
        return self.list_tools()

    def names(self) -> frozenset[str]:
        return frozenset(t.name for t in self._tools())

    def infos(self) -> list[dict[str, str]]:
        return [{k: str(v) for k, v in asdict(t).items()} for t in self._tools()]
