"""Inbound adapter: small read-only HTTP API for the web app (Servers page)."""

from __future__ import annotations

from dataclasses import asdict

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from server_tools.tools.ports.provided import ListTools


def http_routes(list_tools: ListTools) -> list[Route]:
    async def tools(_: Request) -> JSONResponse:
        return JSONResponse([asdict(t) for t in list_tools()])

    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    return [Route("/api/tools", tools), Route("/health", health)]
