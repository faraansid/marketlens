@echo off
title MarketLens
cd /d "%~dp0"

set "PORT=8000"
set "URL=http://localhost:%PORT%"
rem Health checks use 127.0.0.1: "localhost" tries IPv6 first and stalls ~2s on Windows.
set "HEALTH=http://127.0.0.1:%PORT%/api/health"
set "PY=%~dp0backend\.venv\Scripts\python.exe"

echo.
echo   MarketLens - starting...
echo.

rem --- Already running? Just open the browser. ---------------------------------
powershell -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 '%HEALTH%') | Out-Null; exit 0 } catch { exit 1 }"
if %errorlevel%==0 (
    echo   MarketLens is already running. Opening %URL% ...
    start "" "%URL%"
    ping -n 3 127.0.0.1 >nul
    exit /b 0
)

rem --- Checks --------------------------------------------------------------------
if not exist "%PY%" (
    echo   [ERROR] Python environment not found at backend\.venv
    echo   Set it up once with:
    echo     cd backend
    echo     python -m venv .venv
    echo     .venv\Scripts\python -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)
if not exist ".env" (
    echo   [ERROR] .env file not found. Copy .env.example to .env and set SECRET_KEY.
    echo.
    pause
    exit /b 1
)

rem --- Build the web interface if it hasn't been built yet --------------------------
if not exist "frontend\dist\index.html" (
    echo   Building the web interface ^(first run only^)...
    where npm >nul 2>nul
    if errorlevel 1 (
        echo   [ERROR] Node.js is required for the first build. Install it from https://nodejs.org
        pause
        exit /b 1
    )
    pushd frontend
    if not exist "node_modules" call npm install --no-fund --no-audit
    call npm run build
    popd
)

rem --- Open the browser once the server answers (runs in the background) ------------
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "for ($i=0; $i -lt 60; $i++) { try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 '%HEALTH%' | Out-Null; Start-Process '%URL%'; break } catch { Start-Sleep -Seconds 1 } }"

echo   App:  %URL%
echo   Market data refreshes automatically every 30 minutes while this window is open.
echo   Close this window (or press Ctrl+C) to stop MarketLens.
echo.

cd backend
"%PY%" -m uvicorn app.main:app --host 127.0.0.1 --port %PORT%

echo.
echo   MarketLens has stopped.
pause
