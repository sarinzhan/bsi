"""Roles: developer, devops, admin. Combined roles are a union. Admin = developer + devops + users/skills."""

import shutil
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from platform_api.access import create_access_module
from platform_api.access.router import access_router
from platform_api.access.models import ROLE_PERMISSIONS, Permission, Role
from platform_api.access.schemas import NotAllowed, RoleChangeRejected

CONFIG = Path(__file__).resolve().parents[1] / "config/users.yaml"


@pytest.fixture
def access(tmp_path):
    shutil.copy(CONFIG, tmp_path / "users.yaml")
    return create_access_module(tmp_path / "users.yaml", tmp_path / "roles.jsonl"), tmp_path


def test_admin_has_everything_developer_and_devops_have():
    admin = ROLE_PERMISSIONS[Role.ADMIN]
    assert ROLE_PERMISSIONS[Role.DEVELOPER] <= admin and ROLE_PERMISSIONS[Role.DEVOPS] <= admin
    assert Permission.MANAGE_USERS in admin


@pytest.mark.parametrize("user, kind, allowed", [
    ("sarinzha", "read", True), ("sarinzha", "write", False), ("sarinzha", "full", False),  # developer
    ("aibek", "read", True), ("aibek", "write", True), ("aibek", "full", True),  # devops
    ("timur", "write", True), ("dana", "full", True),  # developer+devops, admin
    ("nobody", "read", False), ("sarinzha", "unknown-kind", False),
])
def test_who_can_approve_server_tools(access, user, kind, allowed):
    assert access[0].check.can_approve_tool(user, kind) is allowed


def test_deploys_and_servers_are_devops_work(access):
    check = access[0].check
    assert not check.can("sarinzha", "deploy.approve") and not check.can("sarinzha", "servers.manage")
    assert check.can("aibek", "deploy.approve") and check.can("aibek", "servers.manage")
    assert not check.can("aibek", "code.change")  # pure devops does not get code changes made in their name
    assert check.can("timur", "code.change") and check.can("timur", "deploy.approve")  # both roles
    assert {u.id for u in check.who_can("deploy.approve")} == {"aibek", "timur", "dana"}


def test_only_admins_change_roles_and_it_is_saved_and_logged(access):
    module, d = access
    with pytest.raises(NotAllowed):
        module.admin.set_roles("aibek", "sarinzha", ["developer", "devops"], "on call this month")
    view = module.admin.set_roles("dana", "sarinzha", ["developer", "devops"], "on call this month")
    assert view.roles == ("developer", "devops") and "deploy.approve" in view.permissions
    assert yaml.safe_load((d / "users.yaml").read_text())["users"]["sarinzha"]["roles"] == ["developer", "devops"]
    [change] = module.admin.role_history("sarinzha")
    assert change.added == ("devops",) and change.removed == () and change.by == "Dana M."


def test_rules_no_roles_unknown_role_last_admin_reason(access):
    admin = access[0].admin
    with pytest.raises(RoleChangeRejected, match="at least one role"):
        admin.set_roles("dana", "sarinzha", [], "x")
    with pytest.raises(RoleChangeRejected, match="unknown role"):
        admin.set_roles("dana", "sarinzha", ["root"], "x")
    with pytest.raises(RoleChangeRejected, match="last admin"):
        admin.set_roles("dana", "dana", ["developer"], "stepping down")
    with pytest.raises(RoleChangeRejected, match="why"):
        admin.set_roles("dana", "sarinzha", ["devops"], "")


def test_http(access):
    module, _ = access
    app = FastAPI()
    app.include_router(access_router(module.admin, lambda r: r.headers.get("x-user-id")))
    c = TestClient(app)
    assert c.get("/api/me").status_code == 401
    assert c.get("/api/me", headers={"X-User-Id": "timur"}).json()["roles"] == ["developer", "devops"]
    body = {"roles": ["admin"], "reason": "x"}
    assert c.put("/api/users/aibek/roles", json=body, headers={"X-User-Id": "sarinzha"}).status_code == 403
    assert c.put("/api/users/aibek/roles", json=body, headers={"X-User-Id": "dana"}).status_code == 200
    assert set(c.get("/api/roles").json()) == {"developer", "devops", "admin"}
