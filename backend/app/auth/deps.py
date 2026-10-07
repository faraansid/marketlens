from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import token_digest
from app.config import get_settings
from app.db.models import User, UserSession
from app.db.session import get_db


def current_session(request: Request, db: Session = Depends(get_db)) -> UserSession | None:
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token:
        return None
    sess = db.scalars(select(UserSession).where(UserSession.token_hash == token_digest(token))).first()
    if sess is None or sess.expires_at < datetime.now(timezone.utc):
        return None
    return sess


def require_user(sess: UserSession | None = Depends(current_session), db: Session = Depends(get_db)) -> User:
    if sess is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has expired. Please sign in again.")
    user = db.get(User, sess.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has expired. Please sign in again.")
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can do this.")
    return user
