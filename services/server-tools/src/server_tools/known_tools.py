"""Glue between the two modules: servers.KnownTools answered by the tools catalog.

It lives outside both modules (like main.py), so servers never imports tools.
"""

from __future__ import annotations

from server_tools.tools.domain.catalog import TOOLS


class CatalogToolNames:
    def names(self) -> frozenset[str]:
        return frozenset(TOOLS)
