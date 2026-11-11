"""Sign-in with a password: hashing, sessions, the default admin, must-change, lockout, the HTTP cookie."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from conftest import sample_users
from platform_api.access import create_access_module
from platform_api.access.auth import AuthService
from platform_api.access.passwords import PasswordRejected, hash_password, verify_password
from platform_api.access.repositories.memory import (
    InMemoryCredentialStore, InMemoryRoleChangeLog, InMemorySessionStore, InMemoryUserRepository,
)
from platform_api.access.router import SessionCookie, access_router
from platform_api.access.schemas import LoginFailed, NotAllowed, TooManyAttempts, UserNotFound
from platform_api.access.service import AccessService

GOOD = "correct-horse-battery"


class Clock:
    def __init__(self) -> None:
        self.t = datetime(2026, 11, 11, tzinfo=timezone.utc)
        self.mono = 0.0

    def now(self) -> datetime:
        return self.t

    def monotonic(self) -> float:
        return self.mono


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def auth(clock):
    access = AccessService(InMemoryUserRepository(sample_users()), InMemoryRoleChangeLog())
    service = AuthService(access, InMemoryCredentialStore(), InMemorySessionStore(), timedelta(hours=1),
                          now=clock.now, monotonic=clock.monotonic)
    service.ensure_default_admin("boss", "admin")
    return service


def test_hashes_are_salted_and_verify():
    a, b = hash_password(GOOD), hash_password(GOOD)
    assert a != b and a.startswith("scrypt$")
    assert verify_password(GOOD, a) and not verify_password("wrong", a)
    assert not verify_password(GOOD, "garbage") and not verify_password(GOOD, "md5$1$2$3$aa$bb")


def test_default_admin_must_change_the_password_first(auth):
    token, who = auth.login("Boss ", "admin")  # names are case- and space-insensitive
    assert who.user_id == "boss" and who.must_change_password
    assert auth.session(token).must_change_password
    with pytest.raises(PasswordRejected, match="at least"):
        auth.change_password("boss", "admin", "short")
    with pytest.raises(PasswordRejected, match="current password"):
        auth.change_password("boss", "nope", GOOD)
    new_token = auth.change_password("boss", "admin", GOOD)
    assert auth.session(token) is None  # the old session is gone
    assert not auth.session(new_token).must_change_password
    with pytest.raises(LoginFailed):
        auth.login("boss", "admin")
    assert not auth.ensure_default_admin("boss", "admin")  # restart: the changed password stays


def test_wrong_password_and_unknown_user_look_the_same(auth):
    with pytest.raises(LoginFailed) as a:
        auth.login("boss", "wrong")
    with pytest.raises(LoginFailed) as b:
        auth.login("nobody", "wrong")
    with pytest.raises(LoginFailed):
        auth.login("sarinzha", "")  # exists, but has no password: can not sign in
    assert str(a.value) == str(b.value)


def test_five_wrong_passwords_lock_the_name_for_a_minute(auth, clock):
    for _ in range(5):
        with pytest.raises(LoginFailed):
            auth.login("boss", "wrong")
    with pytest.raises(TooManyAttempts):
        auth.login("boss", "admin")  # even the right password
    clock.mono += 61
    auth.login("boss", "admin")


def test_sessions_expire_and_logout_ends_them(auth, clock):
    token, _ = auth.login("boss", "admin")
    auth.logout(token)
    assert auth.session(token) is None
    token, _ = auth.login("boss", "admin")
    clock.t += timedelta(hours=1)
    assert auth.session(token) is None
    assert auth.session("made-up") is None


def test_admins_add_users_and_reset_passwords(auth):
    auth.change_password("boss", "admin", GOOD)
    with pytest.raises(NotAllowed):
        auth.create_user("sarinzha", "newdev", "", [], "temporary-pass-1")
    with pytest.raises(PasswordRejected):
        auth.create_user("boss", "newdev", "", [], "newdev")
    auth.create_user("boss", "newdev", "New Dev", ["developer"], "temporary-pass-1")
    token, who = auth.login("newdev", "temporary-pass-1")
    assert who.must_change_password
    auth.change_password("newdev", "temporary-pass-1", "my-own-password")

    with pytest.raises(NotAllowed):
        auth.reset_password("newdev", "boss", "taken-over-pass")
    with pytest.raises(UserNotFound):
        auth.reset_password("boss", "ghost", "temporary-pass-2")
    token, _ = auth.login("newdev", "my-own-password")
    auth.reset_password("boss", "newdev", "temporary-pass-2")
    assert auth.session(token) is None  # signed out everywhere
    assert auth.login("newdev", "temporary-pass-2")[1].must_change_password


def make_client(module):
    cookie = SessionCookie()

    def current_user(request: Request):
        token = request.cookies.get(cookie.name)
        s = module.auth.session(token) if token else None
        return s.user_id if s and not s.must_change_password else None

    app = FastAPI()
    app.include_router(access_router(module.admin, current_user, module.auth, cookie))
    return TestClient(app)


def test_http_login_cookie_must_change_and_logout():
    module = create_access_module(users=sample_users(), default_admin=("admin", "admin"))
    c = make_client(module)
    assert c.get("/api/me").status_code == 401
    assert c.post("/api/auth/login", json={"username": "admin", "password": "x"}).status_code == 401
    r = c.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200 and r.json()["must_change_password"]
    set_cookie = r.headers["set-cookie"].lower()
    assert "httponly" in set_cookie and "samesite=strict" in set_cookie
    assert c.get("/api/me").json()["must_change_password"]
    assert c.get("/api/users").status_code == 401  # nothing else until the password is changed
    assert c.post("/api/me/password", json={"current": "admin", "new": "x"}).status_code == 422
    assert c.post("/api/me/password", json={"current": "admin", "new": GOOD}).status_code == 204
    assert c.get("/api/me").json()["roles"] == ["admin"]

    r = c.post("/api/users", json={"id": "newdev", "name": "New Dev", "roles": ["developer"],
                                    "password": "temporary-pass-1"})
    assert r.status_code == 201 and r.json()["roles"] == ["developer"]
    assert c.post("/api/users", json={"id": "newdev", "password": "temporary-pass-1"}).status_code == 422
    assert c.put("/api/users/newdev/password", json={"password": "temporary-pass-2"}).status_code == 204
    assert c.put("/api/users/ghost/password", json={"password": "temporary-pass-2"}).status_code == 404

    assert c.post("/api/auth/logout").status_code == 204
    assert c.get("/api/me").status_code == 401
