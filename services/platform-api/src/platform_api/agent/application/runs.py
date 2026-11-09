"""Use cases: start, resolve, finish, cancel and expire agent runs.

start: check the user -> new run + token -> save (hash only) -> start the container with the token -> running
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Literal

from platform_api.access.ports.provided import AccessCheck
from platform_api.agent.domain.run import InvalidRun, Run, RunStatus, hash_token
from platform_api.agent.ports.provided import RunInfo, RunNotAllowed, RunNotFound, RunRejected, RunReaper, Runs, RunTokens
from platform_api.agent.ports.required import RunRepository, Sandbox, SandboxSpec

USE_CHAT = "chat.use"  # access permission needed to start a run


@dataclass(frozen=True)
class RunSettings:
    mcp_url: str  # server-tools MCP endpoint, as the container sees it
    platform_url: str  # platform-api, as the container sees it (finish, events, model proxy later)
    ttl: timedelta = timedelta(minutes=30)  # the token dies and the container is stopped after this


def _iso(at: datetime) -> str:
    return at.astimezone(timezone.utc).isoformat(timespec="seconds")


def _info(run: Run) -> RunInfo:
    return RunInfo(run.id, run.chat_id, run.system, run.env, run.requested_by, run.status.value,
                   _iso(run.created_at), _iso(run.expires_at), run.error)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RunService(Runs, RunTokens, RunReaper):
    def __init__(self, runs: RunRepository, sandbox: Sandbox, access: AccessCheck, settings: RunSettings,
                 clock: Callable[[], datetime] = _utcnow,
                 new_token: Callable[[], str] = lambda: secrets.token_urlsafe(32),
                 new_id: Callable[[], str] = lambda: "run_" + secrets.token_hex(8)) -> None:
        self._runs, self._sandbox, self._access, self._settings = runs, sandbox, access, settings
        self._clock, self._new_token, self._new_id = clock, new_token, new_id

    # ---- Runs ----

    def start(self, user_id: str, chat_id: str, system: str, env: str) -> RunInfo:
        if not self._access.can(user_id, USE_CHAT):
            raise RunNotAllowed(f"{user_id!r} may not use the agent (needs {USE_CHAT})")
        token, now = self._new_token(), self._clock()
        try:
            run = Run(self._new_id(), chat_id, system, env, user_id, hash_token(token), RunStatus.STARTING,
                      now, now + self._settings.ttl)
        except InvalidRun as e:
            raise RunRejected(str(e)) from e
        self._runs.add(run)
        try:
            self._sandbox.start(SandboxSpec(
                run.id,
                env={
                    "SUPERAI_RUN_ID": run.id,
                    "SUPERAI_RUN_TOKEN": token,
                    "SUPERAI_RUN_DEADLINE": _iso(run.expires_at),
                    "SUPERAI_MCP_URL": self._settings.mcp_url,
                    "SUPERAI_PLATFORM_URL": self._settings.platform_url,
                },
                labels={"superai.run-id": run.id, "superai.system": system, "superai.env": env,
                        "superai.requested-by": user_id},
            ))
        except Exception as e:  # no container = no run; the token is dead from now on
            failed = run.ended(RunStatus.FAILED, f"sandbox did not start: {type(e).__name__}: {e}")
            self._runs.save(failed)
            return _info(failed)
        running = run.running()
        self._runs.save(running)
        return _info(running)

    def cancel(self, user_id: str, run_id: str) -> RunInfo:
        run = self._find(run_id)
        if run.requested_by != user_id:
            raise RunNotAllowed("only the developer who started a run can cancel it")
        if not run.active:
            return _info(run)  # already over: nothing to do
        self._sandbox.stop(run.id)
        cancelled = run.ended(RunStatus.CANCELLED)
        self._runs.save(cancelled)
        return _info(cancelled)

    def get(self, run_id: str) -> RunInfo:
        return _info(self._find(run_id))

    # ---- RunTokens ----

    def resolve(self, token: str) -> RunInfo | None:
        run = self._runs.by_token_hash(hash_token(token)) if token else None
        return _info(run) if run is not None and run.token_usable(self._clock()) else None

    def finish(self, token: str, outcome: Literal["finished", "failed"], error: str | None = None) -> RunInfo:
        run = self._runs.by_token_hash(hash_token(token)) if token else None
        if run is None or not run.token_usable(self._clock()):
            raise RunNotFound("unknown, ended or expired run token")
        ended = run.ended(RunStatus.FINISHED if outcome == "finished" else RunStatus.FAILED, error)
        self._runs.save(ended)
        self._sandbox.stop(run.id)  # normally the container exits by itself; make sure
        return _info(ended)

    # ---- RunReaper ----

    def expire_overdue(self) -> int:
        overdue = self._runs.active_overdue(self._clock())
        for run in overdue:
            try:
                self._sandbox.stop(run.id)
            except Exception:  # still mark it expired: the token must die even if Docker is unhappy
                pass
            self._runs.save(run.ended(RunStatus.EXPIRED, "ran past its deadline"))
        return len(overdue)

    def _find(self, run_id: str) -> Run:
        run = self._runs.get(run_id)
        if run is None:
            raise RunNotFound(run_id)
        return run
