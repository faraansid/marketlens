"""FastAPI application entry point: `uvicorn app.main:app`."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.api import equities, market, patterns, users
from app.auth import router as auth_router
from app.config import get_settings
from app.db.session import get_engine, init_db
from app.logging_config import setup_logging

settings = get_settings()
setup_logging(settings.log_level)
log = logging.getLogger("app")

CSRF_HEADER = "x-requested-with"
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    sched = None
    if settings.run_scheduler_in_api:
        from app.pipeline.scheduler import build_scheduler

        sched = build_scheduler()
        sched.start()
        log.info("In-process scheduler started (every %d min)", settings.refresh_interval_minutes)
    yield
    if sched:
        sched.shutdown(wait=False)


app = FastAPI(
    title=f"{settings.app_name} API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/api/docs",
    redoc_url=None,
    openapi_url=None if settings.is_production else "/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-Requested-With"],
)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    # CSRF defence in depth (cookies are SameSite=Lax already): state-changing
    # API calls must carry a custom header, which cross-site forms cannot set.
    if request.method in UNSAFE and request.url.path.startswith("/api/") and \
            request.headers.get(CSRF_HEADER) != "MarketLens":
        return JSONResponse({"detail": "Request blocked by CSRF protection."}, status_code=403)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


# --- user-friendly error responses ---------------------------------------------
@app.exception_handler(RequestValidationError)
async def _validation(_: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(p) for p in first.get("loc", [])[1:]) or "request"
    return JSONResponse({"detail": f"Invalid {field}: {first.get('msg', 'invalid value')}"}, status_code=422)


@app.exception_handler(OperationalError)
async def _db_down(_: Request, exc: OperationalError):
    log.error("Database operational error: %s", exc)
    return JSONResponse({"detail": "The data store is temporarily unavailable. Please try again shortly."},
                        status_code=503)


@app.exception_handler(SQLAlchemyError)
async def _db_error(_: Request, exc: SQLAlchemyError):
    log.exception("Database error", exc_info=exc)
    return JSONResponse({"detail": "A database error occurred. Please try again."}, status_code=500)


@app.exception_handler(Exception)
async def _unhandled(_: Request, exc: Exception):
    log.exception("Unhandled error", exc_info=exc)
    return JSONResponse({"detail": "Something went wrong on our side. Please try again."}, status_code=500)


# --- routes -------------------------------------------------------------------
app.include_router(auth_router.router)
app.include_router(market.router)
app.include_router(equities.router)
app.include_router(patterns.router)
app.include_router(users.router)


@app.get("/api/health", tags=["health"])
def health():
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    return JSONResponse({"status": "ok" if db_ok else "degraded", "database": db_ok},
                        status_code=200 if db_ok else 503)


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
def api_not_found(path: str):
    raise HTTPException(404, "Not found.")


# --- built frontend (production) -------------------------------------------------
dist = Path(settings.frontend_dist)
if dist.is_dir() and (dist / "index.html").exists():
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")
