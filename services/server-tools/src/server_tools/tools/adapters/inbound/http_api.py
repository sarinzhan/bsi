"""Inbound adapter: small read-only HTTP API for the web app (Servers page), FastAPI."""

from __future__ import annotations

from fastapi import APIRouter

from server_tools.tools.ports.provided import ListTools, ToolInfo


def tools_router(list_tools: ListTools) -> APIRouter:
    router = APIRouter(tags=["tools"])

    @router.get("/api/tools")
    def tools() -> list[ToolInfo]:
        return list_tools()

    @router.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return router
