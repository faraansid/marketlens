"""User management — owner only.

The owner (the account flagged `is_admin`) is the only user who can add,
deactivate, reactivate or remove users. Every endpoint enforces this on the
server via `require_admin`; hiding the UI is not the security boundary.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.serializers import iso
from app.auth.deps import require_admin
from app.auth.security import hash_password, password_problems
from app.db.models import User, UserSession
from app.db.session import get_db

router = APIRouter(prefix="/api/users", tags=["users"])


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9._-]+$")
    fullName: str | None = Field(default=None, max_length=120)
    password: str = Field(min_length=1, max_length=256)


class UserUpdate(BaseModel):
    isActive: bool


def _out(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "fullName": u.full_name,
        "isOwner": u.is_admin,
        "isActive": u.is_active,
        "createdAt": iso(u.created_at),
        "lastLoginAt": iso(u.last_login_at),
    }


@router.get("")
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    users = db.scalars(select(User).order_by(User.is_admin.desc(), User.created_at)).all()
    return [_out(u) for u in users]


@router.post("", status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    problems = password_problems(body.password)
    if problems:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Password needs " + ", ".join(problems) + ".")
    username = body.username.strip().lower()
    if db.scalar(select(func.count()).select_from(User).where(func.lower(User.username) == username)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"The username '{username}' is already taken.")
    user = User(username=username, full_name=(body.fullName or "").strip() or None,
                password_hash=hash_password(body.password), is_admin=False, is_active=True)
    db.add(user)
    db.commit()
    return _out(user)


def _target(db: Session, user_id: int, owner: User) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    if user.id == owner.id or user.is_admin:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The owner account can't be changed here.")
    return user


@router.patch("/{user_id}")
def update_user(user_id: int, body: UserUpdate, db: Session = Depends(get_db), owner: User = Depends(require_admin)):
    user = _target(db, user_id, owner)
    user.is_active = body.isActive
    if not body.isActive:  # sign them out everywhere
        db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db.commit()
    return _out(user)


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int, db: Session = Depends(get_db), owner: User = Depends(require_admin)):
    user = _target(db, user_id, owner)
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db.delete(user)
    db.commit()
