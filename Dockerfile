# MarketLens — single-service image (API + 30-min scheduler + built web UI).
# Used by Railway (see railway.json); works with any Docker host.

# ---- 1. Build the React frontend ---------------------------------------------
FROM node:22-alpine AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY frontend/ ./
RUN npm run build

# ---- 2. Python runtime -------------------------------------------------------
FROM python:3.12-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ENVIRONMENT=production

WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt

COPY backend/ ./
COPY --from=web /app/frontend/dist /app/frontend/dist
RUN mkdir -p /app/backend/data

EXPOSE 8000
# Railway injects $PORT. --proxy-headers + --forwarded-allow-ips make the real
# client IP visible behind Railway's proxy (used by login throttling).
# (Runs as root because Railway volumes are mounted root-owned.)
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
