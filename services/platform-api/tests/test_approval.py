"""Approval module: a person decides before a server tool runs. Nothing is allowed by default."""

import asyncio
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from conftest import make_access
from platform_api.agent import create_agent_module
from platform_api.agent.integrations.fake_sandbox import FakeSandbox
from platform_api.agent.service import RunSettings
from platform_api.approval.router import approvals_router
from platform_api.approval.repositories.memory import InMemoryApprovalRepository
from platform_api.approval.service import ApprovalService
from platform_api.approval.schemas import (
    ApprovalAlreadyDecided, ApprovalNotAllowed, ApprovalRequest,
)
from platform_api.chat import create_chat_module



class World:
    def __init__(self, tmp_path, timeout=timedelta(seconds=5)):
        self.access = make_access()
        agent = create_agent_module(self.access.check, FakeSandbox(),
                                    RunSettings(mcp_url="http://x/mcp/", platform_url="http://y"))
        self.chat = create_chat_module(agent.runs, self.access.check)
        self.approvals = ApprovalService(InMemoryApprovalRepository(), self.chat.events, self.access.check,
                                         timeout=timeout, poll_s=0.01)
        self.chat_id = self.chat.chats.create("sarinzha", "superapp").id

    def req(self, tool="docker_logs", kind="read", server="dev-docker-01", chat_id=None):
        return ApprovalRequest("run_1", chat_id or self.chat_id, tool, kind, server, "docker logs ...", "why restarting")

    def cards(self):
        """The tool call cards in the chat, latest state of each."""
        return [m["call"] for m in self.chat.chats.get("sarinzha", self.chat_id).messages if m["role"] == "tool"]

    def status(self):
        return self.chat.chats.get("sarinzha", self.chat_id).status

    async def answer_when_card_appears(self, user, answer):
        for _ in range(500):
            waiting = [c for c in self.cards() if c["status"] == "waiting"]
            if waiting:
                self.approvals.answer(user, self.chat_id, waiting[0]["id"], answer)
                return waiting[0]["id"]
            await asyncio.sleep(0.01)
        raise AssertionError("no card appeared")


@pytest.fixture
def w(tmp_path):
    return World(tmp_path)


async def test_card_waits_for_a_person_then_runs(w):
    request = asyncio.create_task(w.approvals.request(w.req()))
    call_id = await w.answer_when_card_appears("sarinzha", "allow_once")
    outcome = await request
    assert outcome.allowed and outcome.by == "Sarinzha K. · once" and outcome.call_id == call_id
    [card] = w.cards()
    assert card["status"] == "running" and card["approvedBy"] == "Sarinzha K. · once" and w.status() == "working"
    w.approvals.report(call_id, "done", "exit 0\nOOMKilled")
    assert w.cards()[0]["status"] == "done" and w.cards()[0]["output"] == "exit 0\nOOMKilled"


async def test_allow_reads_for_this_chat_auto_approves_later_reads_on_that_server_only(w):
    first = asyncio.create_task(w.approvals.request(w.req()))
    await w.answer_when_card_appears("sarinzha", "allow_chat")
    assert (await first).by == "Sarinzha K. · reads for this chat"
    second = await w.approvals.request(w.req(tool="docker_ps"))  # no waiting
    assert second.allowed and second.by.startswith("auto")
    other_server = asyncio.create_task(w.approvals.request(w.req(server="dev-docker-02")))
    await asyncio.sleep(0.05)
    assert not other_server.done()  # a grant is per server
    other_server.cancel()


async def test_write_tools_need_devops_and_are_never_granted_for_the_chat(w):
    request = asyncio.create_task(w.approvals.request(w.req("compose_restart", "write")))
    await asyncio.sleep(0.05)
    call_id = w.cards()[0]["id"]
    with pytest.raises(ApprovalNotAllowed, match="devops"):
        w.approvals.answer("sarinzha", w.chat_id, call_id, "allow_once")  # developer only
    w.approvals.answer("aibek", w.chat_id, call_id, "allow_chat")
    assert (await request).by == "Aibek T. · once"  # "for this chat" means once for writes
    again = asyncio.create_task(w.approvals.request(w.req("compose_restart", "write")))
    await asyncio.sleep(0.05)
    assert not again.done()  # asked again
    again.cancel()


async def test_deny_and_no_double_answers(w):
    request = asyncio.create_task(w.approvals.request(w.req()))
    call_id = await w.answer_when_card_appears("sarinzha", "deny")
    outcome = await request
    assert not outcome.allowed and w.cards()[0]["status"] == "denied"
    with pytest.raises(ApprovalAlreadyDecided):
        w.approvals.answer("sarinzha", w.chat_id, call_id, "allow_once")


async def test_no_answer_in_time_means_denied(tmp_path):
    w = World(tmp_path, timeout=timedelta(milliseconds=50))
    outcome = await w.approvals.request(w.req())
    assert not outcome.allowed and outcome.by == "no answer in 5 minutes"
    assert w.cards()[0]["status"] == "denied"


async def test_no_chat_to_ask_in_means_denied_at_once(w):
    outcome = await w.approvals.request(w.req(chat_id="chat-dev"))
    assert not outcome.allowed and outcome.by == "no chat to ask in"


def test_http(w):
    app = FastAPI()
    app.include_router(approvals_router(w.approvals, lambda r: r.headers.get("x-user-id")))
    c = TestClient(app)
    url = f"/api/chats/{w.chat_id}/tool-calls/t_missing/answer"
    assert c.post(url, json={"answer": "deny"}).status_code == 401
    assert c.post(url, json={"answer": "deny"}, headers={"X-User-Id": "sarinzha"}).status_code == 404
