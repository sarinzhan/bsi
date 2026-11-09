"""Servers, access changes and the audit log in Postgres. Skipped without SUPERAI_TEST_DATABASE_URL."""

from pathlib import Path

import psycopg
import pytest

from server_tools.db import migrate
from server_tools.known_tools import CatalogToolNames
from server_tools.servers import create_servers_module
from server_tools.tools import create_tools_module
from server_tools.tools.adapters.outbound.audit_postgres import PostgresAuditLog
from server_tools.tools.adapters.outbound.dev_doubles import AnswerAllApprovals
from server_tools.tools.adapters.outbound.fake_executor import FakeExecutor
from server_tools.tools.adapters.outbound.targets import ServerCatalogTargets
from server_tools.tools.domain.model import RunContext
from server_tools.tools.ports.required import AuditRecord

CONFIG = Path(__file__).resolve().parents[1] / "config/servers.yaml"
READ = ["docker_inspect", "docker_logs", "docker_ps", "docker_stats", "file_read", "folder_list"]


def servers_module(pool, tmp_path):
    return create_servers_module(CONFIG, tmp_path / "unused.jsonl", CatalogToolNames(), pool)


def test_migrations_run_once(pg):
    _, conninfo = pg
    assert migrate(conninfo) == []


def test_empty_database_is_seeded_from_yaml_once_and_the_import_is_logged(pg, tmp_path):
    pool, _ = pg
    servers = servers_module(pool, tmp_path)
    assert [s.name for s in servers.catalog.list()] == ["dev-docker-01", "dev-docker-02", "prod-docker-01",
                                                        "stage-docker-01"]
    assert servers.catalog.get("prod-docker-01").allowed_tools == ("docker_logs", "docker_ps", "docker_stats")
    [imported] = servers.settings.access_history("prod-docker-01")
    assert imported.by == "system" and imported.reason == "imported from servers.yaml"
    servers_module(pool, tmp_path)  # second start: not seeded again
    assert len(servers.settings.access_history("prod-docker-01")) == 1


def test_change_is_saved_and_logged(pg, tmp_path):
    pool, _ = pg
    servers = servers_module(pool, tmp_path)
    info = servers.settings.change_allowed_tools("stage-docker-01", READ, "Sarinzha K.", "stage is read-only now")
    assert list(info.allowed_tools) == READ
    fresh = servers_module(pool, tmp_path)  # a restart reads it back from the database
    assert list(fresh.catalog.get("stage-docker-01").allowed_tools) == READ
    newest, _imported = fresh.settings.access_history("stage-docker-01")
    assert newest.removed == ("compose_restart",) and newest.added == () and newest.by == "Sarinzha K."
    assert newest.at.endswith("+00:00")


def test_database_refuses_ssh_exec_on_prod_even_without_the_app(pg, tmp_path):
    pool, _ = pg
    servers_module(pool, tmp_path)
    with pool.connection() as conn, pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("UPDATE servers SET allowed_tools = allowed_tools || '{ssh_exec}' WHERE name = 'prod-docker-01'")


@pytest.mark.parametrize("sql", [
    "UPDATE access_changes SET reason = 'nothing happened'",
    "DELETE FROM access_changes",
    "TRUNCATE access_changes",
    "UPDATE audit_log SET status = 'done'",
    "DELETE FROM audit_log",
    "TRUNCATE audit_log",
])
def test_history_tables_are_append_only(pg, tmp_path, sql):
    pool, _ = pg
    servers_module(pool, tmp_path)  # seeding writes access_changes rows
    PostgresAuditLog(pool).write(AuditRecord("r", "c", "u", "docker_ps", "dev-docker-01", "-", "u", "done", 0))
    with pool.connection() as conn, pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        conn.execute(sql)


async def test_every_tool_call_is_audited(pg, tmp_path):
    pool, _ = pg
    servers = servers_module(pool, tmp_path)
    tools = create_tools_module(ServerCatalogTargets(servers.catalog), AnswerAllApprovals(allow=True),
                                FakeExecutor(), PostgresAuditLog(pool))
    ctx = RunContext("run-1", "chat-1", "superapp", "dev", "Sarinzha K.")
    assert (await tools.call_tool(ctx, "docker_ps", "dev-docker-01", {})).status == "done"
    assert (await tools.call_tool(ctx, "ssh_exec", "dev-docker-01", {"command": "id", "reason": "x"})).status \
        == "rejected"  # not in dev-docker-01's list
    with pool.connection() as conn:
        rows = conn.execute("SELECT tool, server, status, requested_by FROM audit_log ORDER BY id").fetchall()
    assert rows == [("docker_ps", "dev-docker-01", "done", "Sarinzha K."),
                    ("ssh_exec", "dev-docker-01", "rejected", "Sarinzha K.")]
