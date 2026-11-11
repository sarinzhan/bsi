"""Sign-in: user name + password -> a session token, kept by the browser in an HttpOnly cookie.

- Passwords: scrypt hashes (passwords.py). Sessions: only the SHA-256 of the token is stored.
- Wrong password: the same answer as for an unknown user, and the same work (a dummy hash), so the
  login form does not tell which user names exist.
- 5 wrong passwords for a user name within a minute: that name is locked for the rest of the minute.
- must_change: new users, password resets and the default admin must pick their own password first.
- Changing or resetting a password signs that user out everywhere.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Callable

from platform_api.access.interfaces import CredentialStore, SessionStore
from platform_api.access.models import Credential, Permission, Role, SessionRecord
from platform_api.access.passwords import PasswordRejected, check_new_password, hash_password, verify_password
from platform_api.access.schemas import Auth, LoginFailed, NotAllowed, SignedIn, TooManyAttempts, UserView
from platform_api.access.service import AccessService

MAX_FAILURES = 5
LOCK_SECONDS = 60.0


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class _Throttle:
    """Wrong passwords per user name, in this process (one platform-api process)."""

    def __init__(self, clock: Callable[[], float]) -> None:
        self._clock = clock
        self._failures: dict[str, list[float]] = {}

    def check(self, user_id: str) -> None:
        now = self._clock()
        recent = [t for t in self._failures.get(user_id, []) if now - t < LOCK_SECONDS]
        if recent:
            self._failures[user_id] = recent
        else:
            self._failures.pop(user_id, None)
        if len(recent) >= MAX_FAILURES:
            raise TooManyAttempts("too many wrong passwords: try again in a minute")

    def failed(self, user_id: str) -> None:
        if len(self._failures) > 10_000:  # someone tries many names: forget the oldest
            self._failures.clear()
        self._failures.setdefault(user_id, []).append(self._clock())

    def succeeded(self, user_id: str) -> None:
        self._failures.pop(user_id, None)


class AuthService(Auth):
    def __init__(self, access: AccessService, credentials: CredentialStore, sessions: SessionStore,
                 ttl: timedelta = timedelta(hours=12),
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 monotonic: Callable[[], float] = time.monotonic) -> None:
        self._access, self._credentials, self._sessions = access, credentials, sessions
        self._ttl, self._now = ttl, now
        self._throttle = _Throttle(monotonic)
        self._dummy_hash: str | None = None

    def _start_session(self, user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        self._sessions.add(SessionRecord(_digest(token), user_id, self._now() + self._ttl))
        return token

    def login(self, user_id: str, password: str) -> tuple[str, SignedIn]:
        user_id = user_id.strip().lower()
        self._throttle.check(user_id)
        credential = self._credentials.get(user_id)
        if credential is None:
            self._dummy_hash = self._dummy_hash or hash_password(secrets.token_hex(8))
        ok = verify_password(password, credential.password_hash if credential else self._dummy_hash or "")
        if credential is None or not ok or self._access.name_of(user_id) is None:
            self._throttle.failed(user_id)
            raise LoginFailed("wrong user name or password")
        self._throttle.succeeded(user_id)
        self._sessions.delete_expired(self._now())
        return self._start_session(user_id), SignedIn(user_id, credential.must_change)

    def session(self, token: str) -> SignedIn | None:
        record = self._sessions.get(_digest(token))
        if record is None:
            return None
        if record.expires_at <= self._now():
            self._sessions.delete(record.token_hash)
            return None
        credential = self._credentials.get(record.user_id)
        if credential is None or self._access.name_of(record.user_id) is None:
            return None
        return SignedIn(record.user_id, credential.must_change)

    def logout(self, token: str) -> None:
        self._sessions.delete(_digest(token))

    def change_password(self, user_id: str, current: str, new: str) -> str:
        credential = self._credentials.get(user_id)
        if credential is None or not verify_password(current, credential.password_hash):
            raise PasswordRejected("the current password is wrong")
        check_new_password(new, user_id)
        if new == current:
            raise PasswordRejected("pick a password different from the current one")
        self._credentials.save(Credential(user_id, hash_password(new), must_change=False))
        self._sessions.delete_for_user(user_id)
        return self._start_session(user_id)

    def create_user(self, actor_id: str, user_id: str, name: str, roles: list[str], password: str) -> UserView:
        if not self._access.can(actor_id, Permission.MANAGE_USERS.value):
            raise NotAllowed("only admins can add users")
        check_new_password(password, user_id)
        view = self._access.add_user(actor_id, user_id, name, roles)
        self._credentials.save(Credential(view.id, hash_password(password), must_change=True))
        return view

    def reset_password(self, actor_id: str, user_id: str, password: str) -> None:
        """An admin sets a temporary password; the user must change it at the next sign-in."""
        if not self._access.can(actor_id, Permission.MANAGE_USERS.value):
            raise NotAllowed("only admins can reset passwords")
        self._access.me(user_id)  # UserNotFound
        check_new_password(password, user_id)
        self._credentials.save(Credential(user_id, hash_password(password), must_change=True))
        self._sessions.delete_for_user(user_id)

    def ensure_default_admin(self, user_id: str, password: str) -> bool:
        """First start: user `user_id` with the admin role and this password, to be changed at first sign-in.
        Does nothing once that user has a password, so a changed password is never reset on restart."""
        user_id = user_id.strip().lower()
        self._access.ensure_user(user_id, [Role.ADMIN], "default admin (BSI_ADMIN_USERNAME)")
        if self._credentials.get(user_id) is not None:
            return False
        self._credentials.save(Credential(user_id, hash_password(password), must_change=True))
        return True
