# MarketLens: Indian equity analysis and pattern discovery

MarketLens is a full-stack stock-market analysis app for NSE-listed companies. It includes:

* a market-overview bento grid (indices, India VIX, USD/INR, crude, gold, silver, market breadth);
* a searchable, sortable, server-paginated screener of every NSE-listed company above ₹1,000 Cr market cap;
* a **Breakouts** scanner for VCP, Falling Wedge, horizontal Breakouts (potential / confirmed / failed) and Up/Down trends;
* a stock-detail view with intraday-to-1Y charts, volume, pattern overlays, trend breakdown and technical metrics.

All market data is fetched, validated and analysed **server-side by a scheduled job every 30 minutes**.
The browser only reads results that have already been processed.

> Technical patterns and signals are analytical indicators, not guaranteed predictions or investment advice.

---

## Architecture

```
frontend/  React 19 + Vite + TypeScript + Tailwind v4 + TanStack Query + lightweight-charts
backend/
  app/
    config.py              all settings from env vars (.env)
    main.py                FastAPI app, security middleware, error handlers, serves built SPA
    auth/                  scrypt password hashing, server-side sessions, throttling, master-password changes
    db/                    SQLAlchemy models, session, dialect-aware bulk upsert
    providers/             ← swappable data-provider layer
      base.py                PriceProvider / UniverseProvider interfaces
      yfinance_provider.py   prices, volumes, intraday, share counts (Yahoo via yfinance)
      nse_universe.py        listed-company universe from NSE's official EQUITY_L.csv
      registry.py            selects implementations from PRICE_PROVIDER / UNIVERSE_PROVIDER
      resilience.py          rate limiter + retry with exponential backoff
    analysis/              ← pure technical-analysis engine (no I/O)
      engine.py              PatternDetectionEngine (detector registry, RS calculation)
      indicators.py          SMA/EMA/ATR, fractal swing points, least-squares trendlines
      config.py              every detector threshold (overridable via JSON)
      detectors/             trend.py · falling_wedge.py · vcp.py · breakout.py
    pipeline/              ← scheduled processing
      refresh.py             ingest → validate → filter → metrics → patterns → DB
      scheduler.py           APScheduler (every 30 min, IST), startup catch-up
    worker.py              standalone worker process (`python -m app.worker`)
    api/                   REST endpoints (market, equities, patterns, breakouts)
  scripts/create_user.py   create/update users (no public sign-up)
  tests/                   detector tests on synthetic price series
```

### Data pipeline (every 30 minutes)

```
NSE EQUITY_L.csv ─┐
yfinance prices ──┼─► ingest ─► validate ─► eligible filter ─► metrics ─► pattern engine ─► SQLite/Postgres ─► REST API ─► UI
yfinance shares ──┘    (rate-limited, retried; split/bonus discontinuities trigger a history re-backfill)
```

1. **Universe**: NSE's list of listed equities (refreshed daily). ETFs, REITs, InvITs, mutual funds and
   bonds are published in separate NSE files, so they never enter the universe. Series are limited to
   `EQ,BE`, and a defensive name filter is applied on top.
2. **Prices**: on the first run, 2 years of daily OHLCV are backfilled for every company in batches.
   Each later run downloads the last 5 sessions and upserts them, which also updates the in-progress bar.
   Companies already known to be below the threshold are refreshed only once a day.
3. **Validation**: rows with non-positive or inconsistent prices are dropped. If a stored close and a
   fresh close for the same date differ by more than 5% (a split or bonus), that symbol's history is
   re-downloaded.
4. **Eligibility**: market cap = shares outstanding (from the provider, refreshed weekly) × latest close.
   A company is shown only if its market cap is **≥ ₹1,000 Cr**. Companies whose market cap is unknown are
   excluded, never estimated.
5. **Metrics**: 1D/1W/1M returns, 1-day volume, 1-week average volume, 50-day average volume, 52-week
   range, SMA 20/50/200, ATR %, and an RS rating (1–99 percentile of weighted relative performance vs NIFTY 50).
6. **Pattern detection** runs once per symbol per run, in the background.
7. **Persist**: snapshots are upserted, detections are swapped atomically, and breakout lifecycles
   (potential → confirmed / failed) are tracked across runs in `breakout_signals`.

Failures are isolated per step. A failing step marks the run `partial` and the last good data keeps being
served. A run that cannot evaluate any company never overwrites existing results. The UI shows the
last successful update time and flags a failed latest run.

### Pattern-detection methodology

Each detector's module docstring describes the algorithm in full, and all thresholds live in
`analysis/config.py`.

| Detector | Summary |
|---|---|
| **Trend** (`trend.py`) | Score from −100 to +100 built from price vs SMA50/200 and MA alignment (both ATR-normalised), SMA50 slope, swing structure (HH/HL vs LH/LL), and 60-day momentum. The score maps to Strong Uptrend / Uptrend / Neutral / Downtrend / Strong Downtrend. |
| **Falling Wedge** (`falling_wedge.py`) | Least-squares trendlines through fractal swing highs and lows over several lookbacks. Requires both lines to fall, the upper line to fall faster (convergence, with the apex ahead), enough touches, good fit (R²) and containment. The score also rewards volume contraction. The breakout level slopes with the upper line. |
| **VCP** (`vcp.py`) | Minervini trend template (8 checks, including RS), a base starting at the highest high, and successive pullbacks with decreasing depth (final contraction ≤ 12%, ≤ 75% of the first), plus volume dry-up. The pivot is the high of the final contraction. |
| **Breakout** (`breakout.py`) | Resistance is the highest high of the prior 50 sessions, using only bars at least 5 sessions old. **Confirmed**: close above it with breakout-bar volume ≥ 1.5× the 50-day average. **Potential**: no volume confirmation yet, a retest, or price within 3% below resistance with contracting ATR. **Failed**: broke out within 10 sessions, then closed back more than 1.5% below the level. |

Every detection returns `{symbol, pattern, confidenceScore, detectedAt, currentPrice, support, resistance,
breakoutLevel, volumeRatio, trend, status}` plus pattern-specific metrics. The confidence score measures how
closely the structure matches the definition. It is **not** a probability of success.

To add a detector, subclass `Detector` in `analysis/base.py`, return `Detection` objects, and append the class
to `DEFAULT_DETECTORS` in `analysis/engine.py`.

### REST API (all endpoints except auth and health require a session)

```
GET  /api/market/overview                 instruments + breadth + pattern counts
GET  /api/market/status                   market open/closed, last successful update, last run, next run
GET  /api/equities?search=&sort=&order=&page=&pageSize=&trend=
GET  /api/equities/{symbol}               company, snapshot, technicals, trend breakdown, patterns
GET  /api/equities/{symbol}/chart?tf=     INTRADAY | 1D | 1W (live, cached) · 1M | 3M | 6M | 1Y | 2Y (stored)
GET  /api/patterns?pattern=&status=&minConfidence=&trend=&minMarketCapCr=&maxMarketCapCr=&minPrice=&maxPrice=&minVolumeRatio=&search=&sort=&page=
GET  /api/patterns/summary
GET  /api/patterns/{symbol}
GET  /api/breakouts?status=&pattern=&minConfidence=&minVolumeRatio=&page=
GET  /api/jobs                             recent pipeline runs
POST /api/jobs/refresh                     admin: trigger a refresh now
POST /api/auth/login | /logout | /change-password · GET /api/auth/me
GET  /api/health
```

Sort fields for `/api/equities`: `name, symbol, price, oneDayChange, oneWeekChange, volume, avgVolumeWeek,
marketCap, trendScore, rsRating`. Interactive docs are at `/api/docs` outside production.

### Users and the owner

Sign-in is by **username**. There is no public sign-up. There is a single **owner** account (set with
`create_user --owner`). Only the owner sees the **Users** page and can add, deactivate, reactivate or remove
users, and trigger a manual data refresh. The server enforces this on every `/api/users` endpoint. Hiding the
page is not the security boundary.

```
GET    /api/users            owner: list users
POST   /api/users            owner: add a user {username, fullName?, password}
PATCH  /api/users/{id}       owner: {isActive} (deactivating signs the user out everywhere)
DELETE /api/users/{id}       owner: remove a user (the owner account itself can't be removed)
```

### Security

* Passwords are hashed with scrypt (salted, with parameters stored alongside the hash). Plaintext passwords are never stored or logged.
* Sessions are server-side. The random token lives in an `HttpOnly`, `SameSite=Lax` cookie (`Secure` in production),
  and only its SHA-256 digest is stored in the database. "Remember me" gives 30 days; otherwise the session lasts 12 hours.
* Login errors are generic, timing is equalised for unknown users, and failed attempts are throttled per IP and per account.
* State-changing requests must carry a custom header (CSRF defence), and CORS is restricted.
* **Master password.** "Change password" on the sign-in page sets a new password for any username,
  provided the caller knows the master password. There is no email reset. Only the master password's scrypt hash is stored
  (in `app_state`). Set or rotate it with `python -m scripts.set_master_password`. Wrong attempts are
  throttled per IP and **globally** (default 10 per hour across all clients), because a guessed master
  password unlocks every account. Use a long master password. A change signs that user out everywhere.
* Secrets come only from environment variables. The app refuses to start without a strong `SECRET_KEY`.

---

## Running locally

Requirements: Python 3.12, Node.js 20+.

```bash
# 1. configure
cp .env.example .env          # then set SECRET_KEY (see the comment in the file)

# 2. backend
cd backend
python -m venv .venv
.venv\Scripts\activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m scripts.create_user --username you --owner                          # prompts for a password
python -m scripts.set_master_password                                          # enables "Change password"

# 3. frontend
cd ../frontend
npm install
npm run build                 # FastAPI serves frontend/dist
```

Start the API, which also runs the 30-minute scheduler in-process by default:

```bash
cd backend
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

Open http://localhost:8000. For frontend development with hot reload, run `npm run dev` in `frontend/` and
open http://localhost:5173. Vite proxies `/api` to port 8000.

**First run:** the initial refresh backfills 2 years of history for about 2,500 NSE companies and fetches share
counts. That takes roughly 15–20 minutes, depending on the provider. You can watch progress in the server
log or run it explicitly with `python -m app.worker --once`. Later runs take a few minutes.

## Deploying to Railway

The repo is ready for Railway. `railway.json` tells Railway to build the `Dockerfile`, which compiles the web
UI and runs the API with the 30-minute scheduler in one service. Railway's `$PORT` is used automatically, and
`/api/health` is the health check.

1. **New project → Deploy from GitHub repo** → pick this repository.
2. **Add persistent storage.** Without it, the database is wiped on every deploy. Choose one:
   * **Volume (simplest):** right-click the service → *Attach volume* → mount path `/data`. The app detects
     `RAILWAY_VOLUME_MOUNT_PATH` and stores SQLite there. Nothing else to set.
   * **Postgres:** add a Postgres database to the project, then set the service variable
     `DATABASE_URL=${{Postgres.DATABASE_URL}}`. `postgres://` URLs are converted automatically.
3. **Variables** (service → *Variables*):

   | Variable | Required | Value |
   |---|---|---|
   | `SECRET_KEY` | yes | a random string of at least 32 characters |
   | `OWNER_USERNAME` | first deploy | the owner's username |
   | `OWNER_PASSWORD` | first deploy | the owner's password |
   | `OWNER_NAME` | no | display name |
   | `MASTER_PASSWORD` | first deploy | enables "Change password" on the sign-in page |

   The owner and master password are created **only if they don't exist yet**. Changing these variables later
   does not overwrite anything. Change passwords inside the app instead.
4. **Settings → Networking → Generate Domain**, then open it and sign in with the owner account.

The first market-data refresh starts automatically after deploy and takes about 15–20 minutes (2 years of
history for about 2,500 NSE companies). The dashboard fills in when it finishes. The deploy logs show progress.

Notes:
* Keep **1 replica**. The scheduler runs in-process, and login throttling is in-memory.
* The first backfill uses roughly 0.5–1 GB of RAM. Make sure your Railway plan allows that.
* Yahoo Finance can rate-limit cloud IPs more than home connections. The pipeline retries with backoff, and the
  app keeps serving the last good data if a refresh fails.

### Production notes

* Set `ENVIRONMENT=production` (the Docker image does this). This enables Secure cookies and hides the API docs.
* Run the API with `RUN_SCHEDULER_IN_API=false` and a separate worker (`python -m app.worker`), so the API can
  scale independently. The `job_runs` table prevents overlapping runs across processes.
* For PostgreSQL, set `DATABASE_URL` (`postgres://`, `postgresql://` or `postgresql+psycopg://`). The driver is included.
* Set a long master password and a strong owner password. Both are recoverable only with server access (the scripts above).
* Login throttling is in-process. Back it with Redis if you run several API instances.

### Swapping the data provider

Implement `PriceProvider` and/or `UniverseProvider` from `app/providers/base.py`, register the factory in
`app/providers/registry.py`, and set `PRICE_PROVIDER` / `UNIVERSE_PROVIDER`. The pipeline, analysis engine,
API and UI don't need to change.

### Data caveats

* yfinance uses Yahoo Finance's public endpoints. It is unofficial, may be delayed, and may rate-limit. The provider
  layer retries with backoff, but for commercial use you should switch to a licensed feed using the interface above.
* During market hours the latest bar is an in-progress session, so its volume (and volume ratios) are partial.
* Missing values are shown as "—". The app never estimates or invents a missing metric.

### Tests

```bash
cd backend && .venv\Scripts\python -m pytest
```
