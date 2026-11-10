"""The tools module wired to the real servers, agent, chat and approval modules (in-process, no HTTP)."""

import asyncio
import shutil
from pathlib import Path

import pytest

from platform_api.access import create_access_module
from platform_api.agent import create_agent_module
from platform_api.agent.integrations.fake_sandbox import FakeSandbox
from platform_api.agent.service import RunSettings
from platform_api.approval.repositories.memory import InMemoryApprovalRepository
from platform_api.approval.service import ApprovalService
from platform_api.chat import create_chat_module
from platform_api.servers import create_servers_module
from platform_api.tools import create_tools_module
from platform_api.tools.integrations.fake_ssh import FakeExecutor
from platform_api.tools.integrations.platform_modules import ApprovalCards, RunTokenAuthority, ServerCatalogTargets
from platform_api.wiring import ChatRunListener, ToolCatalog

CONFIG = Path(__file__).resolve().parents[1] / "config"


class Audit:
    def __init__(self):
        self.records = []

    def write(self, record):
        self.records.append(record)


class Platform:
    """Everything main.py wires, minus HTTP."""

    def __init__(self, d: Path):
        for name in ("users.yaml", "servers.yaml"):
            shutil.copy(CONFIG / name, d / name)
        self.access = create_access_module(d / "users.yaml", d / "roles.jsonl")
        catalog = ToolCatalog()
        self.servers = create_servers_module(d / "servers.yaml", d / "access.jsonl", catalog, self.access.check)
        self.sandbox = FakeSandbox()
        listener = ChatRunListener()
        self.agent = create_agent_module(self.access.check, self.sandbox,
                                         RunSettings(mcp_url="http://platform-api:8000/mcp/", platform_url="x"),
                                         listener=listener)
        self.chat = create_chat_module(self.agent.runs, self.access.check)
        listener.chat = self.chat.runner
        self.approvals = ApprovalService(InMemoryApprovalRepository(), self.chat.events, self.access.check, poll_s=0.01)
        self.executor, self.audit = FakeExecutor(), Audit()
        self.tools = create_tools_module(ServerCatalogTargets(self.servers.catalog), ApprovalCards(self.approvals),
                                         self.executor, self.audit)
        catalog.list_tools = self.tools.list_tools
        self.authority = RunTokenAuthority(self.agent.tokens)

    def cards(self, chat_id):
        return [m["call"] for m in self.chat.chats.get("sarinzha", chat_id).messages if m["role"] == "tool"]


@pytest.fixture
def p(tmp_path):
    return Platform(tmp_path)


async def start_run(p):
    chat_id = p.chat.chats.create("sarinzha", "superapp").id
    p.chat.chats.send("sarinzha", chat_id, "why is orders restarting?")
    ctx = await p.authority.resolve(p.sandbox.started[-1].env["BSI_RUN_TOKEN"])
    return chat_id, ctx


async def test_a_tool_call_goes_through_the_card_in_the_chat(p):
    chat_id, ctx = await start_run(p)
    assert (ctx.system, ctx.env, ctx.chat_id, ctx.requested_by) == ("superapp", "dev", chat_id, "sarinzha")
    call = asyncio.create_task(p.tools.call_tool(ctx, "docker_ps", "dev-docker-01", {}))
    for _ in range(200):
        if p.cards(chat_id):
            break
        await asyncio.sleep(0.01)
    [card] = p.cards(chat_id)
    assert card["status"] == "waiting" and card["command"].startswith("docker ps")
    p.approvals.answer("sarinzha", chat_id, card["id"], "allow_once")
    outcome = await call
    assert outcome.status == "done" and len(p.executor.calls) == 1
    [card] = p.cards(chat_id)
    assert card["status"] == "done" and card["output"].startswith("exit 0")
    assert p.audit.records[-1].approved_by == "Sarinzha K. · once" and p.audit.records[-1].run_id == ctx.run_id


async def test_server_settings_apply_to_the_next_call(p):
    chat_id, ctx = await start_run(p)
    p.servers.settings.change_allowed_tools("dev-docker-01", ["docker_logs"], "aibek", "logs only")
    outcome = await p.tools.call_tool(ctx, "docker_ps", "dev-docker-01", {})
    assert outcome.status == "rejected" and "not allowed on dev-docker-01" in outcome.text
    assert p.cards(chat_id) == []  # rejected before anyone is asked


async def test_tool_names_for_server_settings_come_from_the_tools_catalog(p):
    with pytest.raises(Exception, match="unknown tools: rm_rf"):
        p.servers.settings.change_allowed_tools("dev-docker-01", ["rm_rf"], "aibek", "x")
    assert len(p.servers.catalog.tools()) == 11


async def test_a_finished_run_token_no_longer_works(p):
    _, ctx = await start_run(p)
    token = p.sandbox.started[-1].env["BSI_RUN_TOKEN"]
    p.agent.tokens.finish(token, "finished")
    assert await p.authority.resolve(token) is None
