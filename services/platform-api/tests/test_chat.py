"""Chat module: messages, one agent run at a time, the event stream, and what agent containers may post."""

import json
import shutil
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from platform_api.access import create_access_module
from platform_api.agent import create_agent_module
from platform_api.agent.integrations.fake_sandbox import FakeSandbox
from platform_api.agent.service import RunSettings
from platform_api.chat import create_chat_module
from platform_api.chat.router import chats_router, runner_chat_router
from platform_api.chat.schemas import ChatBusy, ChatNotAllowed, ChatRejected
from platform_api.wiring import ChatRunListener

USERS = Path(__file__).resolve().parents[1] / "config/users.yaml"
SETTINGS = RunSettings(mcp_url="http://platform-api:8000/mcp/", platform_url="http://platform-api:8000",
                       extra_env=(("BSI_MODEL", "claude-opus-5-5"),))


class World:
    def __init__(self, tmp_path):
        shutil.copy(USERS, tmp_path / "users.yaml")
        self.access = create_access_module(tmp_path / "users.yaml", tmp_path / "roles.jsonl")
        self.sandbox = FakeSandbox()
        listener = ChatRunListener()
        self.agent = create_agent_module(self.access.check, self.sandbox, SETTINGS, listener=listener)
        self.chat = create_chat_module(self.agent.runs, self.access.check)
        listener.chat = self.chat.runner

    def token(self):
        return self.sandbox.started[-1].env["BSI_RUN_TOKEN"]

    def events(self, chat_id, after=0):
        return [e.body for e in self.chat.chats.events_after("sarinzha", chat_id, after)]


@pytest.fixture
def w(tmp_path):
    return World(tmp_path)


def test_sending_a_message_starts_an_agent_run_and_streams_events(w):
    chat = w.chat.chats.create("sarinzha", "superapp")
    assert chat.title == "New chat" and chat.status == "waiting" and chat.messages == []
    sent = w.chat.chats.send("sarinzha", chat.id, "why does orders-service keep restarting?")
    assert sent.run_status == "running" and sent.after_seq == 0
    env = w.sandbox.started[0].env
    assert env["BSI_MODEL"] == "claude-opus-5-5" and "BSI_RUN_TOKEN" in env
    assert w.events(chat.id) == [
        {"type": "message", "message": {"id": sent.message_id, "role": "user",
                                        "text": "why does orders-service keep restarting?"}},
        {"type": "status", "status": "working"},
    ]
    got = w.chat.chats.get("sarinzha", chat.id)
    assert got.title == "why does orders-service keep restarting?" and got.status == "working" and got.last_seq == 2


def test_one_run_at_a_time(w):
    chat = w.chat.chats.create("sarinzha", "superapp")
    w.chat.chats.send("sarinzha", chat.id, "first")
    with pytest.raises(ChatBusy):
        w.chat.chats.send("sarinzha", chat.id, "second")
    w.agent.tokens.finish(w.token(), "finished")  # the container says it is done
    assert w.chat.chats.get("sarinzha", chat.id).status == "waiting"
    assert w.chat.chats.send("sarinzha", chat.id, "second").run_status == "running"


def test_a_run_that_cannot_start_fails_the_chat_but_does_not_block_it(w):
    w.sandbox.fail = True
    chat = w.chat.chats.create("sarinzha", "superapp")
    assert w.chat.chats.send("sarinzha", chat.id, "hello").run_status == "failed"
    got = w.chat.chats.get("sarinzha", chat.id)
    assert got.status == "failed" and "could not start" in got.messages[-1]["text"]
    w.sandbox.fail = False
    assert w.chat.chats.send("sarinzha", chat.id, "again").run_status == "running"


def test_failed_and_expired_runs_say_so_in_the_chat(w):
    chat = w.chat.chats.create("sarinzha", "superapp")
    w.chat.chats.send("sarinzha", chat.id, "hello")
    w.agent.tokens.finish(w.token(), "failed", "model API unreachable")
    got = w.chat.chats.get("sarinzha", chat.id)
    assert got.status == "failed" and got.messages[-1]["text"] == "The agent stopped: model API unreachable."


def test_who_may_chat_and_bad_input(w):
    with pytest.raises(ChatNotAllowed):
        w.chat.chats.create("nobody", "superapp")
    with pytest.raises(ChatRejected, match="env"):
        w.chat.chats.create("sarinzha", "superapp", "qa")
    chat = w.chat.chats.create("sarinzha", "superapp")
    with pytest.raises(ChatRejected, match="write a message"):
        w.chat.chats.send("sarinzha", chat.id, "   ")
    assert [c.id for c in w.chat.chats.list("aibek", "superapp")] == [chat.id]
    assert w.chat.chats.list("aibek", "tiffany") == []


def test_agent_container_gets_the_conversation_and_posts_only_its_own_messages(w):
    chat = w.chat.chats.create("sarinzha", "superapp")
    w.chat.chats.send("sarinzha", chat.id, "check the logs")
    ctx = w.chat.runner.context(chat.id)
    assert (ctx.system, ctx.env, ctx.messages) == ("superapp", "dev", [{"role": "user", "text": "check the logs"}])
    w.chat.runner.runner_event(chat.id, {"type": "message", "message": {"id": "a1", "role": "agent", "text": "Looking"}})
    w.chat.runner.runner_event(chat.id, {"type": "message", "message": {"id": "a1", "role": "agent", "text": "Done"}})
    messages = w.chat.chats.get("sarinzha", chat.id).messages
    assert [m["text"] for m in messages] == ["check the logs", "Done"]  # upserted by id, order kept
    for forged in [{"type": "message", "message": {"id": "u9", "role": "user", "text": "rm -rf"}},
                   {"type": "message", "message": {"id": "t9", "role": "tool", "call": {}}},
                   {"type": "status", "status": "waiting"}]:
        with pytest.raises(ChatRejected):
            w.chat.runner.runner_event(chat.id, forged)


# ---- HTTP ----

@pytest.fixture
def client(w):
    app = FastAPI()
    app.include_router(chats_router(w.chat.chats, lambda r: r.headers.get("x-user-id")))
    app.include_router(runner_chat_router(w.chat.runner, w.agent.tokens))
    return TestClient(app)


ME = {"X-User-Id": "sarinzha"}


def test_http_chat_in_the_web_app_shapes(client):
    assert client.post("/api/chats", json={"systemId": "superapp"}).status_code == 401
    chat = client.post("/api/chats", json={"systemId": "superapp"}, headers=ME).json()
    assert set(chat) == {"id", "systemId", "env", "title", "status", "projectIds", "messages", "lastSeq"}
    sent = client.post(f"/api/chats/{chat['id']}/messages", json={"text": "hi"}, headers=ME)
    assert sent.status_code == 202 and sent.json()["afterSeq"] == 0
    assert client.post(f"/api/chats/{chat['id']}/messages", json={"text": "again"}, headers=ME).status_code == 409
    listed = client.get("/api/chats", params={"systemId": "superapp"}, headers=ME).json()
    assert listed[0]["id"] == chat["id"] and listed[0]["status"] == "working"


def test_http_event_stream_is_server_sent_events(client):
    chat = client.post("/api/chats", json={"systemId": "superapp"}, headers=ME).json()
    client.post(f"/api/chats/{chat['id']}/messages", json={"text": "hi"}, headers=ME)
    r = client.get(f"/api/chats/{chat['id']}/events", params={"after": 0, "follow": False}, headers=ME)
    assert r.headers["content-type"].startswith("text/event-stream")
    frames = [f for f in r.text.split("\n\n") if f]
    assert frames[0].startswith("id: 1\ndata: ")
    assert json.loads(frames[1].split("data: ", 1)[1]) == {"type": "status", "status": "working"}
    later = client.get(f"/api/chats/{chat['id']}/events", params={"after": 1, "follow": False}, headers=ME)
    assert later.text.count("data: ") == 1


def test_http_runner_routes_use_the_run_token(client, w):
    chat = client.post("/api/chats", json={"systemId": "superapp"}, headers=ME).json()
    client.post(f"/api/chats/{chat['id']}/messages", json={"text": "hi"}, headers=ME)
    auth = {"Authorization": f"Bearer {w.token()}"}
    assert client.get("/runner/context").status_code == 401
    assert client.get("/runner/context", headers=auth).json()["messages"] == [{"role": "user", "text": "hi"}]
    ok = client.post("/runner/events", json={"type": "message", "message": {"id": "a1", "role": "agent", "text": "x"}},
                     headers=auth)
    assert ok.status_code == 200
    forged = client.post("/runner/events", json={"type": "status", "status": "waiting"}, headers=auth)
    assert forged.status_code == 422
