"""Master password used to change any user's password (replaces email resets).

Only a scrypt hash is stored (in the `app_state` table); the plaintext never
appears in source, config files or logs. Set or rotate it with:

    python -m scripts.set_master_password
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.auth.security import hash_password, verify_password
from app.db.models import AppState

_KEY = "master_password_hash"


def is_configured(db: Session) -> bool:
    row = db.get(AppState, _KEY)
    return bool(row and row.value and row.value.get("hash"))


def verify_master(db: Session, candidate: str) -> bool:
    row = db.get(AppState, _KEY)
    return bool(row and row.value and verify_password(candidate, row.value.get("hash", "")))


def set_master(db: Session, plaintext: str) -> None:
    value = {"hash": hash_password(plaintext)}
    row = db.get(AppState, _KEY)
    if row:
        row.value = value
    else:
        db.add(AppState(key=_KEY, value=value))
