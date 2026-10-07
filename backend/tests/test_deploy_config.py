"""Deployment configuration: database URL resolution and first-run bootstrap."""
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-test-secret-key-0123456789")

import pytest

from app.config import Settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("DATABASE_URL", "RAILWAY_VOLUME_MOUNT_PATH"):
        monkeypatch.delenv(k, raising=False)


def _settings(**kw) -> Settings:
    return Settings(_env_file=None, secret_key="x" * 40, **kw)


@pytest.mark.parametrize("raw", [
    "postgres://u:p@host:5432/db",
    "postgresql://u:p@host:5432/db",
    "postgresql+psycopg://u:p@host:5432/db",
])
def test_postgres_urls_are_normalised(raw):
    assert _settings(database_url=raw).database_url == "postgresql+psycopg://u:p@host:5432/db"


def test_volume_path_used_for_sqlite():
    s = _settings(railway_volume_mount_path="/data")
    assert s.database_url == "sqlite:////data/marketlens.db"


def test_explicit_url_beats_volume():
    s = _settings(database_url="sqlite:///x.db", railway_volume_mount_path="/data")
    assert s.database_url == "sqlite:///x.db"


def test_local_default():
    assert _settings().database_url.endswith("/backend/data/marketlens.db")
