"""Authentication endpoints (cookie-based server-side sessions).

* The session token lives in an HttpOnly, SameSite=Lax cookie (Secure in
  production) and is never readable by JavaScript.
* Login errors are deliberately generic (no user enumeration), timing is
  equalised for unknown users, and repeated failures are throttled.
* "Remember me" issues a persistent cookie (REMEMBER_ME_TTL_DAYS); otherwise a
  browser-session cookie with a shorter server-side expiry is used.
* Passwords are changed with the master password (see `app.auth.master`);
  there is no email-based reset.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.auth import master
from app.auth.deps import current_session, require_user
from app.auth.security import (
    dummy_verify,
    hash_password,
    new_token,
    password_problems,
    token_digest,
    verify_password,
)
from app.auth.throttle import LoginThrottle
from app.config import get_settings
from app.db.models import User, UserSession
from app.db.session import get_db

log = logging.getLogger("auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])
_settings = get_settings()
# Per-account limit is strict; the per-IP limit is looser so that one user's
# typos behind a shared NAT don't lock out everyone else on that address.
throttle = LoginThrottle(_settings.login_max_attempts, _settings.login_lockout_minutes * 60)
ip_throttle = LoginThrottle(_settings.login_max_attempts * 4, _settings.login_lockout_minutes * 60)
# Master-password attempts: a global cap across all clients (10 wrong guesses
# per hour), since a guessed master password unlocks every account.
MASTER_GLOBAL_KEY = "master:global"
master_throttle = LoginThrottle(_settings.master_max_failures_per_hour, 3600)


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    remember: bool = False


class UserOut(BaseModel):
    id: int
    username: str | None
    fullName: str | None
    isAdmin: bool


class ChangePasswordIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    masterPassword: str = Field(min_length=1, max_length=256)
    newPassword: str = Field(min_length=1, max_length=256)


def _user_out(u: User) -> UserOut:
    return UserOut(id=u.id, username=u.username, fullName=u.full_name, isAdmin=u.is_admin)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    s = get_settings()
    ident = body.username.strip().lower()
    ip_key, id_key = f"ip:{_client_ip(request)}", f"id:{ident}"
    wait = max(throttle.retry_after(id_key), ip_throttle.retry_after(ip_key))
    if wait:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many sign-in attempts. Try again in {max(1, wait // 60)} minute(s).",
            headers={"Retry-After": str(wait)},
        )

    user = db.scalars(select(User).where(func.lower(User.username) == ident)).first()
    if user is None:
        dummy_verify()
        ok = False
    else:
        ok = verify_password(body.password, user.password_hash)
    if not ok or not user or not user.is_active:
        throttle.fail(id_key)
        ip_throttle.fail(ip_key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password.")

    throttle.reset(id_key)
    token = new_token()
    now = datetime.now(timezone.utc)
    ttl = timedelta(days=s.remember_me_ttl_days) if body.remember else timedelta(hours=s.session_ttl_hours)
    db.add(UserSession(token_hash=token_digest(token), user_id=user.id, created_at=now, expires_at=now + ttl,
                       remember=body.remember, user_agent=(request.headers.get("user-agent") or "")[:255],
                       ip=_client_ip(request)))
    user.last_login_at = now
    # Opportunistic cleanup of this user's expired sessions.
    db.execute(delete(UserSession).where(UserSession.user_id == user.id, UserSession.expires_at < now))
    db.commit()

    response.set_cookie(
        s.session_cookie_name, token,
        max_age=int(ttl.total_seconds()) if body.remember else None,
        httponly=True, secure=s.secure_cookies, samesite="lax", path="/",
    )
    return _user_out(user)


@router.post("/logout", status_code=204)
def logout(response: Response, sess: UserSession | None = Depends(current_session), db: Session = Depends(get_db)):
    if sess is not None:
        db.execute(delete(UserSession).where(UserSession.id == sess.id))
        db.commit()
    response.delete_cookie(get_settings().session_cookie_name, path="/")
    response.status_code = 204
    return response


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(require_user)):
    return _user_out(user)


class MyPasswordIn(BaseModel):
    currentPassword: str = Field(min_length=1, max_length=256)
    newPassword: str = Field(min_length=1, max_length=256)


@router.post("/me/password")
def change_my_password(
    body: MyPasswordIn,
    user: User = Depends(require_user),
    sess: UserSession | None = Depends(current_session),
    db: Session = Depends(get_db),
):
    """Signed-in user changes their own password (requires the current one).
    Other sessions of this user are signed out; the current one stays."""
    key = f"self-pw:{user.id}"
    wait = throttle.retry_after(key)
    if wait:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"Too many attempts. Try again in {max(1, wait // 60)} minute(s).",
                            headers={"Retry-After": str(wait)})
    if not verify_password(body.currentPassword, user.password_hash):
        throttle.fail(key)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect.")
    problems = password_problems(body.newPassword)
    if problems:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "New password needs " + ", ".join(problems) + ".")
    throttle.reset(key)
    user.password_hash = hash_password(body.newPassword)
    keep_id = sess.id if sess else -1
    db.execute(delete(UserSession).where(UserSession.user_id == user.id, UserSession.id != keep_id))
    db.commit()
    log.info("User %r changed their password", user.username)
    return {"message": "Password changed."}


@router.post("/change-password")
def change_password(body: ChangePasswordIn, request: Request, db: Session = Depends(get_db)):
    """Change a user's password by proving knowledge of the master password.

    Wrong master passwords are throttled per IP *and* globally (across all
    clients), because a guessed master password unlocks every account.
    """
    ip_key = f"master-ip:{_client_ip(request)}"
    wait = max(master_throttle.retry_after(MASTER_GLOBAL_KEY), ip_throttle.retry_after(ip_key))
    if wait:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many attempts. Try again in {max(1, wait // 60)} minute(s).",
            headers={"Retry-After": str(wait)},
        )
    if not master.is_configured(db):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Password changes are disabled until the owner sets a master password.")
    problems = password_problems(body.newPassword)
    if problems:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "New password needs " + ", ".join(problems) + ".")

    user = db.scalars(select(User).where(func.lower(User.username) == body.username.strip().lower())).first()
    master_ok = master.verify_master(db, body.masterPassword)
    if not master_ok or user is None or not user.is_active:
        master_throttle.fail(MASTER_GLOBAL_KEY)
        ip_throttle.fail(ip_key)
        log.warning("Failed master-password change attempt for username %r from %s", body.username, _client_ip(request))
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Username or master password is incorrect.")

    user.password_hash = hash_password(body.newPassword)
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))  # sign out everywhere
    db.commit()
    log.info("Password changed via master password for user %r", user.username)
    return {"message": "Password changed. You can now sign in with your new password."}
