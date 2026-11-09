"""Users and role changes in Postgres. Skipped without SUPERAI_TEST_DATABASE_URL."""

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import exc, text

from platform_api.access import create_access_module
from platform_api.access.ports.provided import RoleChangeRejected
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

    from platform_api.agent.adapters.outbound.postgres import PostgresRunRepository
    from platform_api.agent.domain.run import Run, RunStatus, hash_token

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
