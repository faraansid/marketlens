"""Password hashing and token helpers.

* Passwords: scrypt (memory-hard KDF from the standard library) with a random
  16-byte salt per password; parameters are stored with the hash so they can
  be raised later without invalidating existing hashes.
* Session / reset tokens: 32 random bytes sent to the client; only their
  SHA-256 digest is stored, so a database leak does not leak live sessions.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

_N, _R, _P, _DKLEN = 2**14, 8, 1, 64


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN, maxmem=64 * 1024 * 1024)
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return f"scrypt${_N}${_R}${_P}${b64(salt)}${b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_b64, dk_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        salt, expected = base64.b64decode(salt_b64), base64.b64decode(dk_b64)
        dk = hashlib.scrypt(password.encode(), salt=salt, n=int(n), r=int(r), p=int(p),
                            dklen=len(expected), maxmem=64 * 1024 * 1024)
        return hmac.compare_digest(dk, expected)
    except Exception:  # noqa: BLE001 - malformed hash => no match
        return False


# Used to equalise timing when the user does not exist.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def dummy_verify() -> None:
    verify_password("not-the-password", _DUMMY_HASH)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def password_problems(pw: str) -> list[str]:
    """No strength rules by owner decision; a password only has to be non-empty."""
    return [] if pw else ["at least 1 character"]
