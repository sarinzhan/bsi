"""Sign-in with a password: hashing, sessions, the default admin, must-change, lockout, the JWT."""

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
from platform_api.access.router import access_router, signed_in_as
from platform_api.access.schemas import LoginFailed, NotAllowed, TooManyAttempts, UserNotFound
from platform_api.access.service import AccessService

GOOD = "correct-horse-battery"
SECRET = "test-secret-" + "x" * 32


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
    service = AuthService(access, InMemoryCredentialStore(), InMemorySessionStore(), SECRET, timedelta(hours=1),
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
    def current_user(request: Request):
        s = signed_in_as(module.auth, request)
        return s.user_id if s and not s.must_change_password else None

    app = FastAPI()
    app.include_router(access_router(module.admin, current_user, module.auth))
    return TestClient(app)


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_tokens_are_signed_jwts_and_end_with_their_session(auth):
    import jwt as pyjwt

    token, _ = auth.login("boss", "admin")
    claims = pyjwt.decode(token, SECRET, algorithms=["HS256"], options={"verify_exp": False})  # fake clock
    assert claims["sub"] == "boss" and claims["exp"] - claims["iat"] == 3600 and claims["jti"]
    forged = pyjwt.encode({**claims, "sub": "dana"}, "another-secret-" + "y" * 32, algorithm="HS256")
    assert auth.session(forged) is None  # wrong signature
    unsigned = pyjwt.encode(claims, None, algorithm="none")
    assert auth.session(unsigned) is None  # alg "none" is never accepted
    same_secret_no_session = pyjwt.encode({**claims, "jti": "other"}, SECRET, algorithm="HS256")
    assert auth.session(same_secret_no_session) is None  # signed right, but never issued (or revoked)
    assert auth.session("not-a-jwt") is None
    assert auth.session(token).user_id == "boss"


def test_a_short_secret_is_refused():
    access = AccessService(InMemoryUserRepository(()), InMemoryRoleChangeLog())
    with pytest.raises(ValueError, match="secret"):
        AuthService(access, InMemoryCredentialStore(), InMemorySessionStore(), "short")


def test_http_login_token_must_change_and_logout():
    module = create_access_module(users=sample_users(), default_admin=("admin", "admin"))
    c = make_client(module)
    assert c.get("/api/me").status_code == 401
    assert c.post("/api/auth/login", json={"username": "admin", "password": "x"}).status_code == 401
    r = c.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200 and r.json()["user"]["must_change_password"]
    assert "set-cookie" not in r.headers
    token = r.json()["token"]
    assert c.get("/api/me", headers=bearer(token)).json()["must_change_password"]
    assert c.get("/api/me", headers={"Authorization": f"Basic {token}"}).status_code == 401
    assert c.get("/api/users", headers=bearer(token)).status_code == 401  # nothing else until it is changed
    r = c.post("/api/me/password", json={"current": "admin", "new": "x"}, headers=bearer(token))
    assert r.status_code == 422
    r = c.post("/api/me/password", json={"current": "admin", "new": GOOD}, headers=bearer(token))
    assert r.status_code == 200 and not r.json()["user"]["must_change_password"]
    assert c.get("/api/me", headers=bearer(token)).status_code == 401  # the old token ended
    token = r.json()["token"]
    assert c.get("/api/me", headers=bearer(token)).json()["roles"] == ["admin"]

    r = c.post("/api/users", json={"id": "newdev", "name": "New Dev", "roles": ["developer"],
                                    "password": "temporary-pass-1"}, headers=bearer(token))
    assert r.status_code == 201 and r.json()["roles"] == ["developer"]
    assert c.post("/api/users", json={"id": "newdev", "password": "temporary-pass-1"},
                  headers=bearer(token)).status_code == 422
    assert c.put("/api/users/newdev/password", json={"password": "temporary-pass-2"},
                 headers=bearer(token)).status_code == 204
    assert c.put("/api/users/ghost/password", json={"password": "temporary-pass-2"},
                 headers=bearer(token)).status_code == 404

    assert c.post("/api/auth/logout", headers=bearer(token)).status_code == 204
    assert c.get("/api/me", headers=bearer(token)).status_code == 401
