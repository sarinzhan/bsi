"""platform-api over HTTP: platform-api's /runner routes, called with this run's token."""

from __future__ import annotations

from typing import Any

import httpx

from agent_runner.interfaces import Context, Platform


class PlatformApi(Platform):
    def __init__(self, base_url: str, run_token: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, headers={"Authorization": f"Bearer {run_token}"},
                                         timeout=30, transport=transport)  # transport: tests only

    async def context(self) -> Context:
        r = await self._client.get("/runner/context")
        r.raise_for_status()
        b = r.json()
        return Context(b["chatId"], b["system"], b["env"], b["messages"])

    async def post(self, event: dict[str, Any]) -> None:
        (await self._client.post("/runner/events", json=event)).raise_for_status()

    async def finish(self, outcome: str, error: str | None = None) -> None:
        body: dict[str, Any] = {"outcome": outcome}
        if error:
            body["error"] = error[:2000]
        (await self._client.post("/runner/finish", json=body)).raise_for_status()
