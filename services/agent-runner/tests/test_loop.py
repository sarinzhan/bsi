"""The agent loop, with fakes for the model, the tools and platform-api."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from agent_runner import loop, prompts
from agent_runner.integrations.platform_http import PlatformApi
from agent_runner.integrations.scripted_model import ScriptedModel
from agent_runner.interfaces import Context, ModelUnavailable, Reply, ToolCall, ToolResult, ToolSpec

REPO = Path(__file__).resolve().parents[3]


class FakePlatform:
    def __init__(self, messages=None):
        self.events, self.finished = [], None
        self._messages = messages if messages is not None else [{"role": "user", "text": "why is orders restarting?"}]

    async def context(self):
        return Context("c_1", "superapp", "dev", self._messages)

    async def post(self, event):
        self.events.append(event)

    async def finish(self, outcome, error=None):
        self.finished = (outcome, error)

    def texts(self):
        return [e["message"]["text"] for e in self.events]


class FakeTools:
    def __init__(self, result=ToolResult("exit 0\n{\"State\":\"restarting\"}", False)):
        self.calls, self._result = [], result

    async def list(self):
        return [ToolSpec("docker_ps", "Containers.", {"type": "object", "properties": {"server": {"type": "string"}}})]

    async def call(self, name, arguments):
        self.calls.append((name, arguments))
        return self._result


def system(system, env, chat):
    return f"system={system} env={env}"


async def test_tool_call_then_answer():
    platform, tools = FakePlatform(), FakeTools()
    assert await loop.run(ScriptedModel(), tools, platform, system) == "finished"
    assert tools.calls == [("docker_ps", {"server": "dev-docker-01"})]
    assert platform.texts()[0].startswith("(scripted) Checking")  # what it is about to do
    assert "restarting" in platform.texts()[1] and platform.finished == ("finished", None)


async def test_denied_call_goes_back_to_the_model_as_an_error():
    seen = []

    class Recording(ScriptedModel):
        async def next(self, system, messages, tools):
            seen.append(messages[-1])
            return await super().next(system, messages, tools)

    tools = FakeTools(ToolResult("Denied by the developer (Sarinzha K.). Do not retry.", True))
    platform = FakePlatform()
    assert await loop.run(Recording(), tools, platform, system) == "finished"
    result = seen[1]["content"][0]
    assert result["is_error"] is True and result["tool_use_id"] == "toolu_scripted_1" and "Denied" in result["content"]
    assert "was not allowed" in platform.texts()[-1]


async def test_thinking_and_all_content_is_passed_back_unchanged():
    turns = []

    class Model:
        async def next(self, system, messages, tools):
            turns.append(list(messages))
            if len(turns) == 1:
                content = [{"type": "thinking", "thinking": "", "signature": "sig"},
                           {"type": "tool_use", "id": "t1", "name": "docker_ps", "input": {"server": "x"}}]
                return Reply(content, "tool_use", "", [ToolCall("t1", "docker_ps", {"server": "x"})])
            return Reply([{"type": "text", "text": "done"}], "end_turn", "done")

    await loop.run(Model(), FakeTools(), FakePlatform(), system)
    assert turns[1][1]["content"][0] == {"type": "thinking", "thinking": "", "signature": "sig"}


async def test_failures_always_end_the_run_with_a_reason():
    class Refuses:
        async def next(self, *a):
            return Reply([], "refusal", "")

    class Down:
        async def next(self, *a):
            raise ModelUnavailable("the Anthropic API key is missing or wrong")

    class Loops:
        async def next(self, *a):
            return Reply([], "tool_use", "", [ToolCall("t", "docker_ps", {})])

    for model, why in [(Refuses(), "declined"), (Down(), "API key"), (Loops(), "stopped after 3 steps")]:
        platform = FakePlatform()
        assert await loop.run(model, FakeTools(), platform, system, max_turns=3) == "failed"
        assert platform.finished[0] == "failed" and why in platform.finished[1]


async def test_stops_before_the_deadline_and_needs_a_user_message():
    now = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)
    platform = FakePlatform()
    await loop.run(ScriptedModel(), FakeTools(), platform, system, deadline=now + timedelta(seconds=10),
                   clock=lambda: now)
    assert platform.finished == ("failed", "the run reached its time limit")
    empty = FakePlatform(messages=[{"role": "assistant", "text": "hello"}])
    await loop.run(ScriptedModel(), FakeTools(), empty, system)
    assert empty.finished[0] == "failed" and "no user message" in empty.finished[1]


async def test_platform_adapter_uses_the_run_token():
    seen = []

    def platform_api(request):
        seen.append(request)
        if request.url.path == "/runner/context":
            return httpx.Response(200, json={"chatId": "c_1", "system": "superapp", "env": "dev",
                                             "messages": [{"role": "user", "text": "hi"}]})
        return httpx.Response(200, json={})

    api = PlatformApi("http://platform-api:8000", "tok", httpx.MockTransport(platform_api))
    ctx = await api.context()
    await api.finish("failed", "x" * 5000)
    assert ctx.system == "superapp" and all(r.headers["authorization"] == "Bearer tok" for r in seen)
    assert len(json.loads(seen[1].content)["error"]) == 2000


def test_system_prompt_is_built_from_the_repo_instructions():
    system_prompt = prompts.load(REPO / "agent")
    text = system_prompt("superapp", "dev", "c_1")
    assert "BSI agent" in text and "# Server tools reference" in text and "System: superapp. Environment: dev" in text
    assert prompts.load(REPO / "missing")("a", "b", "c").startswith(prompts.FALLBACK)
