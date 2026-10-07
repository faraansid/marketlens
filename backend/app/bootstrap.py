"""First-run bootstrap from environment variables.

Hosted platforms (e.g. Railway) have no interactive shell for the
`scripts/` CLI, so the owner account and master password can be created from
env vars on startup:

    OWNER_USERNAME, OWNER_PASSWORD, OWNER_NAME (optional), MASTER_PASSWORD

Rules:
* Runs only when the thing is missing: if an owner already exists, or a
  master password is already set, the env vars are ignored (they never
  overwrite data, so you can safely leave them set or remove them).
* Values are never logged.
"""
from __future__ import annotations

import logging

from sqlalchemy import func, select

from app.auth import master
from app.auth.security import hash_password
from app.config import get_settings
from app.db.models import User
from app.db.session import session_scope

log = logging.getLogger("bootstrap")


def run_bootstrap() -> None:
    s = get_settings()
    with session_scope() as db:
        has_owner = db.scalar(select(func.count()).select_from(User).where(User.is_admin.is_(True)))
        if not has_owner:
            if s.owner_username and s.owner_password:
                username = s.owner_username.strip().lower()
                user = db.scalars(select(User).where(func.lower(User.username) == username)).first()
                if user is None:
                    user = User(username=username)
                    db.add(user)
                user.full_name = s.owner_name or user.full_name or username
                user.password_hash = hash_password(s.owner_password)
                user.is_admin = True
                user.is_active = True
                log.info("Bootstrap: created owner account %r from environment", username)
            else:
                log.warning("No owner account exists. Set OWNER_USERNAME and OWNER_PASSWORD "
                            "(Railway: service > Variables) and redeploy to create one.")

        if not master.is_configured(db):
            if s.master_password:
                master.set_master(db, s.master_password)
                log.info("Bootstrap: master password set from environment")
            else:
                log.warning("No master password set; 'Change password' on the sign-in page is disabled. "
                            "Set MASTER_PASSWORD and redeploy to enable it.")
