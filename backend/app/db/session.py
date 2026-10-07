"""Engine / session factory. SQLite by default (WAL mode), Postgres via DATABASE_URL."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is None:
        url = get_settings().database_url
        kwargs: dict = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            db_path = url.split("sqlite:///", 1)[-1]
            if db_path and db_path != ":memory:":
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        _engine = create_engine(url, **kwargs)

        if url.startswith("sqlite"):

            @event.listens_for(_engine, "connect")
            def _sqlite_pragmas(dbapi_conn, _):  # pragma: no cover - driver hook
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA synchronous=NORMAL")
                cur.execute("PRAGMA foreign_keys=ON")
                cur.close()

        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, autoflush=False)
    return _engine


def SessionLocal() -> Session:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for background jobs and scripts."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app.db import models  # noqa: F401  (register models)
    from app.db.base import Base

    engine = get_engine()
    Base.metadata.create_all(engine)
    _migrate_users_email_nullable(engine)


def _migrate_users_email_nullable(engine: Engine) -> None:
    """Idempotent migration: users.email became optional.

    SQLite can't drop NOT NULL in place, so the table is rebuilt (the
    documented 12-step procedure, with foreign keys off during the swap).
    """
    from sqlalchemy import text

    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("ALTER TABLE users ALTER COLUMN email DROP NOT NULL"))
            return
        if engine.dialect.name != "sqlite":
            return
        cols = {r[1]: r[3] for r in conn.execute(text("PRAGMA table_info(users)"))}
        if not cols.get("email"):  # already nullable (or table missing)
            return
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        cur.execute("PRAGMA foreign_keys=OFF")
        cur.executescript(
            """
            BEGIN;
            CREATE TABLE users_new (
                id INTEGER NOT NULL PRIMARY KEY,
                email VARCHAR(255),
                username VARCHAR(64),
                full_name VARCHAR(120),
                password_hash VARCHAR(255) NOT NULL,
                is_active BOOLEAN NOT NULL,
                is_admin BOOLEAN NOT NULL,
                created_at DATETIME NOT NULL,
                last_login_at DATETIME
            );
            INSERT INTO users_new (id, email, username, full_name, password_hash, is_active, is_admin, created_at, last_login_at)
                SELECT id, email, username, full_name, password_hash, is_active, is_admin, created_at, last_login_at FROM users;
            DROP TABLE users;
            ALTER TABLE users_new RENAME TO users;
            CREATE UNIQUE INDEX ix_users_username ON users (username);
            CREATE UNIQUE INDEX ix_users_email ON users (email);
            COMMIT;
            """
        )
        cur.execute("PRAGMA foreign_keys=ON")
        bad = cur.execute("PRAGMA foreign_key_check").fetchall()
        if bad:
            raise RuntimeError(f"users migration left dangling foreign keys: {bad[:5]}")
    finally:
        raw.close()
