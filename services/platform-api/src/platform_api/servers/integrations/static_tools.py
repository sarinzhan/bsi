"""For tests: a fixed list of tool names. In the app, wiring.py answers KnownTools from the
tools module's catalog."""

from __future__ import annotations

from platform_api.servers.interfaces import KnownTools


class StaticKnownTools(KnownTools):
    def __init__(self, names: frozenset[str]) -> None:
        self._names = frozenset(names)

    def names(self) -> frozenset[str]:
        return self._names

    def infos(self) -> list[dict[str, str]]:
        return [{"name": n} for n in sorted(self._names)]
