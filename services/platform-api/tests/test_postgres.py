"""Users and role changes in Postgres. Skipped without BSI_TEST_DATABASE_URL."""

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import exc, text

from platform_api.access import create_access_module
from platform_api.access.schemas import RoleChangeRejected
from platform_api.db import MIGRATIONS, migrate

CONFIG = Path(__file__).resolve().parents[1] / "config/users.yaml"


def access_module(engine, tmp_path):
    return create_access_module(CONFIG, tmp_path / "unused.jsonl", engine)


def test_database_is_at_the_newest_migration_and_migrating_again_is_a_no_op(pg):
    engine, url = pg
    migrate(url)
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    with engine.connect() as conn:
        versions = conn.scalars(text("SELECT version_num FROM alembic_version")).all()
    assert versions == [ScriptDirectory.from_config(config).get_current_head()]


def test_empty_database_is_seeded_from_yaml_once(pg, tmp_path):
    engine, _ = pg
    access = access_module(engine, tmp_path)
    assert {u.id for u in access.admin.list_users()} == {"sarinzha", "aibek", "timur", "dana"}
    assert access.check.can_approve_tool("aibek", "write") and not access.check.can_approve_tool("sarinzha", "write")
    [imported] = access.admin.role_history("dana")
    assert imported.by == "system" and imported.added == ("admin",)
    access_module(engine, tmp_path)
    assert len(access.admin.role_history("dana")) == 1


def test_role_change_is_saved_and_logged(pg, tmp_path):
    engine, _ = pg
    access = access_module(engine, tmp_path)
    access.admin.set_roles("dana", "sarinzha", ["developer", "devops"], "on call this month")
    fresh = access_module(engine, tmp_path)
    assert fresh.admin.me("sarinzha").roles == ("developer", "devops")
    newest, _imported = fresh.admin.role_history("sarinzha")
    assert newest.added == ("devops",) and newest.by == "Dana M." and newest.at.endswith("+00:00")


def test_last_admin_rule_still_holds(pg, tmp_path):
    engine, _ = pg
    with pytest.raises(RoleChangeRejected, match="last admin"):
        access_module(engine, tmp_path).admin.set_roles("dana", "dana", ["developer"], "stepping down")


@pytest.mark.parametrize("sql", [
    "UPDATE users SET roles = '{}' WHERE id = 'dana'",        # every user keeps at least one role
    "UPDATE users SET roles = '{root}' WHERE id = 'dana'",    # only known roles
])
def test_database_checks_roles(pg, tmp_path, sql):
    engine, _ = pg
    access_module(engine, tmp_path)
    with engine.begin() as conn, pytest.raises(exc.IntegrityError, match="roles_valid"):
        conn.execute(text(sql))


@pytest.mark.parametrize("sql", ["UPDATE role_changes SET reason = 'x'", "DELETE FROM role_changes",
                                 "TRUNCATE role_changes"])
def test_role_changes_are_append_only(pg, tmp_path, sql):
    engine, _ = pg
    access_module(engine, tmp_path)
    with engine.begin() as conn, pytest.raises(exc.DBAPIError, match="append-only"):
        conn.execute(text(sql))


# ---- agent module: runs ----

def test_runs_are_stored_with_the_token_hash_and_found_by_it(pg, tmp_path):
    from datetime import datetime, timedelta, timezone

    from platform_api.agent.repositories.postgres import PostgresRunRepository
    from platform_api.agent.models import Run, RunStatus, hash_token

    engine, _ = pg
    repo = PostgresRunRepository(engine)
    t0 = datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)
    run = Run("run_1", "chat_1", "superapp", "dev", "sarinzha", hash_token("tok"), RunStatus.STARTING,
              t0, t0 + timedelta(minutes=30))
    repo.add(run)
    repo.save(run.running())
    assert repo.get("run_1").status is RunStatus.RUNNING
    assert repo.by_token_hash(hash_token("tok")).id == "run_1" and repo.by_token_hash(hash_token("x")) is None
    assert repo.active_overdue(t0 + timedelta(minutes=29)) == []
    assert [r.id for r in repo.active_overdue(t0 + timedelta(minutes=30))] == ["run_1"]
    repo.save(repo.get("run_1").ended(RunStatus.EXPIRED, "late"))
    assert repo.active_overdue(t0 + timedelta(hours=1)) == []
    with engine.connect() as conn:
        assert "tok" not in str(conn.execute(text("SELECT * FROM runs")).all())


# ---- servers module ----

SERVERS = Path(__file__).resolve().parents[1] / "config/servers.yaml"
READ = ["docker_inspect", "docker_logs", "docker_ps", "docker_stats", "file_read", "folder_list"]


def servers_module(engine, tmp_path):
    from platform_api.servers import create_servers_module
    from platform_api.servers.integrations.static_tools import StaticKnownTools

    known = StaticKnownTools(frozenset(READ + ["compose_restart", "ssh_exec"]))
    return create_servers_module(SERVERS, tmp_path / "unused.jsonl", known, access_module(engine, tmp_path).check,
                                 engine)


def test_servers_are_seeded_from_yaml_once_and_the_import_is_logged(pg, tmp_path):
    engine, _ = pg
    servers = servers_module(engine, tmp_path)
    assert [s.name for s in servers.catalog.list()] == ["dev-docker-01", "dev-docker-02", "prod-docker-01",
                                                        "stage-docker-01"]
    [imported] = servers.settings.access_history("prod-docker-01")
    assert imported.by == "system" and imported.reason == "imported from servers.yaml"
    servers_module(engine, tmp_path)
    assert len(servers.settings.access_history("prod-docker-01")) == 1


def test_server_access_change_is_saved_and_logged(pg, tmp_path):
    engine, _ = pg
    servers_module(engine, tmp_path).settings.change_allowed_tools("stage-docker-01", READ, "aibek", "read-only")
    fresh = servers_module(engine, tmp_path)
    assert list(fresh.catalog.get("stage-docker-01").allowed_tools) == READ
    newest, _imported = fresh.settings.access_history("stage-docker-01")
    assert newest.removed == ("compose_restart",) and newest.by == "aibek" and newest.at.endswith("+00:00")


def test_database_refuses_ssh_exec_on_prod_even_without_the_app(pg, tmp_path):
    engine, _ = pg
    servers_module(engine, tmp_path)
    with engine.begin() as conn, pytest.raises(exc.IntegrityError, match="no_ssh_exec_on_prod"):
        conn.execute(text("UPDATE servers SET allowed_tools = allowed_tools || '{ssh_exec}' "
                          "WHERE name = 'prod-docker-01'"))


@pytest.mark.parametrize("sql", ["UPDATE access_changes SET reason = 'x'", "DELETE FROM access_changes",
                                 "TRUNCATE access_changes"])
def test_access_changes_are_append_only(pg, tmp_path, sql):
    engine, _ = pg
    servers_module(engine, tmp_path)
    with engine.begin() as conn, pytest.raises(exc.DBAPIError, match="append-only"):
        conn.execute(text(sql))


# ---- chat and approval modules ----

def test_chat_messages_are_upserted_in_place_and_events_stream_in_order(pg):
    from datetime import datetime, timezone

    from platform_api.chat.repositories.postgres import PostgresChatRepository
    from platform_api.chat.models import Chat, ChatMessage, ChatStatus

    engine, _ = pg
    repo = PostgresChatRepository(engine)
    chat = Chat("c_1", "superapp", "dev", "New chat", ChatStatus.WAITING, "sarinzha", datetime.now(timezone.utc))
    repo.add(chat)
    s1 = repo.record("c_1", {"type": "message", "message": {"id": "m1", "role": "user", "text": "hi"}},
                     ChatMessage("c_1", "m1", "user", {"id": "m1", "role": "user", "text": "hi"}))
    s2 = repo.record("c_1", {"type": "message", "message": {"id": "t1", "role": "tool", "call": {"status": "waiting"}}},
                     ChatMessage("c_1", "t1", "tool", {"id": "t1", "role": "tool", "call": {"status": "waiting"}}))
    s3 = repo.record("c_1", {"type": "message", "message": {"id": "a1", "role": "agent", "text": "ok"}},
                     ChatMessage("c_1", "a1", "agent", {"id": "a1", "role": "agent", "text": "ok"}))
    repo.record("c_1", {"type": "message", "message": {"id": "t1", "role": "tool", "call": {"status": "done"}}},
                ChatMessage("c_1", "t1", "tool", {"id": "t1", "role": "tool", "call": {"status": "done"}}),
                chat.with_status(ChatStatus.WORKING))
    assert [m.id for m in repo.messages("c_1")] == ["m1", "t1", "a1"]  # t1 keeps its place
    assert repo.messages("c_1")[1].body["call"]["status"] == "done"
    assert repo.get("c_1").status is ChatStatus.WORKING
    assert [s for s, _ in repo.events_after("c_1", s1, 10)][:2] == [s2, s3] and repo.last_seq("c_1") > s3
    with engine.begin() as conn, pytest.raises(exc.DBAPIError, match="append-only"):
        conn.execute(text("UPDATE chat_events SET body = '{}'"))


def test_approvals_and_read_grants_are_stored(pg):
    from datetime import datetime, timedelta, timezone

    from platform_api.approval.repositories.postgres import PostgresApprovalRepository
    from platform_api.approval.models import Answer, Approval, ApprovalStatus

    engine, _ = pg
    repo = PostgresApprovalRepository(engine)
    now = datetime.now(timezone.utc)
    a = Approval("t_1", "run_1", "c_1", "docker_logs", "read", "dev-docker-01", "docker logs x", "why",
                 ApprovalStatus.PENDING, now, now + timedelta(minutes=5))
    repo.add(a)
    repo.save(a.decided(Answer.ALLOW_CHAT, "sarinzha", "Sarinzha K."))
    assert repo.get("t_1").note == "Sarinzha K. · reads for this chat"
    assert not repo.has_read_grant("c_1", "dev-docker-01")
    repo.add_read_grant("c_1", "dev-docker-01", "sarinzha")
    repo.add_read_grant("c_1", "dev-docker-01", "sarinzha")  # twice is fine
    assert repo.has_read_grant("c_1", "dev-docker-01") and not repo.has_read_grant("c_1", "dev-docker-02")


# ---- tools module: the audit log ----

def test_every_tool_call_is_audited_and_the_audit_log_is_append_only(pg):
    import asyncio

    from platform_api.tools import create_tools_module
    from platform_api.tools.repositories.postgres import PostgresAuditLog
    from platform_api.tools.integrations.dev_doubles import AnswerAllApprovals, StaticTargets
    from platform_api.tools.integrations.fake_ssh import FakeExecutor
    from platform_api.tools.models import RunContext

    engine, _ = pg
    tools = create_tools_module(StaticTargets(Path(__file__).resolve().parent / "fixtures/servers.yaml"),
                                AnswerAllApprovals(allow=True), FakeExecutor(), PostgresAuditLog(engine))
    ctx = RunContext("run-1", "chat-1", "superapp", "dev", "Sarinzha K.")
    assert asyncio.run(tools.call_tool(ctx, "docker_ps", "dev-docker-01", {})).status == "done"
    assert asyncio.run(tools.call_tool(ctx, "ssh_exec", "dev-docker-01", {"command": "id", "reason": "x"})).status \
        == "rejected"
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT tool, status, requested_by FROM audit_log ORDER BY id")).all()
    assert [tuple(r) for r in rows] == [("docker_ps", "done", "Sarinzha K."), ("ssh_exec", "rejected", "Sarinzha K.")]
    for sql in ["UPDATE audit_log SET status = 'done'", "DELETE FROM audit_log", "TRUNCATE audit_log"]:
        with engine.begin() as conn, pytest.raises(exc.DBAPIError, match="append-only"):
            conn.execute(text(sql))
