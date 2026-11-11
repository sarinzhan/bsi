"""Password hashing with scrypt (Python standard library, no extra dependency).

Stored as "scrypt$<n>$<r>$<p>$<salt hex>$<hash hex>", so the cost can be raised later without breaking
old hashes: each one says how it was made.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

_N, _R, _P = 2**14, 8, 1  # 16 MB memory, ~50 ms per hash
_LEN = 32
MIN_LENGTH, MAX_LENGTH = 10, 200


class PasswordRejected(ValueError):
    """The new password breaks a rule, or the current one is wrong. Message says which."""


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_LEN)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        kind, n, r, p, salt, digest = stored.split("$")
        if kind != "scrypt":
            return False
        expected = bytes.fromhex(digest)
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p),
                                dklen=len(expected), maxmem=64 * 1024 * 1024)
    except ValueError:
        return False
    return hmac.compare_digest(actual, expected)


def check_new_password(password: str, user_id: str) -> None:
    if len(password) < MIN_LENGTH:
        raise PasswordRejected(f"the password needs at least {MIN_LENGTH} characters")
    if len(password) > MAX_LENGTH:
        raise PasswordRejected(f"the password can have at most {MAX_LENGTH} characters")
    if password.strip().lower() == user_id.lower():
        raise PasswordRejected("the password can not be the user name")
