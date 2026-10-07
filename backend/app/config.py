"""Application configuration.

All settings are read from environment variables (or a `.env` file in the
project root / backend directory). Secrets are never hardcoded: SECRET_KEY has
no usable default in production and the app refuses to start without it.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(PROJECT_DIR / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- General -----------------------------------------------------------
    app_name: str = "MarketLens"
    environment: str = Field(default="development", description="development | production")
    log_level: str = "INFO"

    # --- Security ----------------------------------------------------------
    secret_key: str = Field(default="", description="Required. Used to sign/derive tokens.")
    session_cookie_name: str = "ml_session"
    session_ttl_hours: int = 12  # browser-session login
    remember_me_ttl_days: int = 30  # "remember me" login
    cookie_secure: bool | None = None  # defaults to True in production
    login_max_attempts: int = 5
    login_lockout_minutes: int = 15
    master_max_failures_per_hour: int = 10  # global cap on wrong master-password attempts

    # --- Database ----------------------------------------------------------
    # Resolution order (see `_resolve_database_url`):
    #   1. DATABASE_URL (e.g. Railway Postgres; postgres:// is normalised)
    #   2. SQLite on a mounted volume (Railway sets RAILWAY_VOLUME_MOUNT_PATH)
    #   3. SQLite under backend/data (local development)
    database_url: str = ""
    railway_volume_mount_path: str | None = None

    # --- First-run bootstrap (for hosts without an interactive shell) --------
    # Used only when no owner / master password exists yet; never overwrites.
    owner_username: str | None = None
    owner_password: str | None = None
    owner_name: str | None = None
    master_password: str | None = None

    # --- Scheduler ---------------------------------------------------------
    run_scheduler_in_api: bool = True  # set False when running the separate worker process
    refresh_interval_minutes: int = 30
    run_on_startup_if_stale: bool = True
    job_stale_after_minutes: int = 45  # a "running" job older than this is considered dead

    # --- Market-data providers --------------------------------------------
    price_provider: str = "yfinance"
    universe_provider: str = "nse_equity_list"
    nse_equity_list_url: str = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
    universe_series: str = "EQ,BE"  # NSE series treated as ordinary listed company shares
    universe_refresh_hours: int = 24
    min_market_cap_cr: float = 1000.0  # ₹ crore
    shares_refresh_days: int = 7
    shares_max_per_run: int = 4000  # bootstrap (no share counts yet) covers the whole universe
    shares_steady_per_run: int = 300  # afterwards stale counts are refreshed gradually, keeping runs short

    history_period: str = "2y"
    download_batch_size: int = 80
    download_threads: int = 8
    provider_min_interval_seconds: float = 0.25  # simple rate limit between provider calls
    provider_max_retries: int = 4
    provider_backoff_seconds: float = 2.0
    intraday_cache_seconds: int = 120

    benchmark_symbol: str = "^NSEI"

    # --- Analysis ----------------------------------------------------------
    pattern_config_file: str | None = None  # optional JSON overriding detector thresholds

    # --- Frontend ----------------------------------------------------------
    frontend_dist: str = str(PROJECT_DIR / "frontend" / "dist")
    cors_origins: str = "http://localhost:5173,http://localhost:8000"

    @field_validator("environment")
    @classmethod
    def _env(cls, v: str) -> str:
        return v.lower().strip()

    @model_validator(mode="after")
    def _resolve_database_url(self) -> "Settings":
        url = (self.database_url or "").strip()
        if url:
            # Railway/Heroku style URLs -> SQLAlchemy + psycopg 3 driver.
            if url.startswith("postgres://"):
                url = "postgresql+psycopg://" + url[len("postgres://"):]
            elif url.startswith("postgresql://"):
                url = "postgresql+psycopg://" + url[len("postgresql://"):]
        elif self.railway_volume_mount_path:
            url = f"sqlite:///{(Path(self.railway_volume_mount_path) / 'marketlens.db').as_posix()}"
        else:
            url = f"sqlite:///{(BACKEND_DIR / 'data' / 'marketlens.db').as_posix()}"
        self.database_url = url
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def secure_cookies(self) -> bool:
        return self.is_production if self.cookie_secure is None else self.cookie_secure

    @property
    def series_list(self) -> list[str]:
        return [s.strip().upper() for s in self.universe_series.split(",") if s.strip()]

    @property
    def min_market_cap_inr(self) -> float:
        return self.min_market_cap_cr * 1e7  # 1 crore = 10,000,000


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if not s.secret_key or len(s.secret_key) < 32:
        raise RuntimeError(
            "SECRET_KEY is missing or too short (min 32 chars). "
            "Set it as an environment variable (Railway: service > Variables) "
            "or copy .env.example to .env locally."
        )
    return s
