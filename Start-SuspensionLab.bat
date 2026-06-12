@echo off
echo ========================================================
echo        SUSPENSIONLAB PRO - NATIVE WINDOWS LAUNCHER
echo ========================================================
echo.

cd /d "%~dp0"

if not exist "venv" (
    echo [1/5] Creating Python virtual environment...
    python -m venv venv
)

call venv\Scripts\activate.bat

if not exist "venv\installed.flag" (
    echo [2/5] Installing dependencies... This will only happen once.
    pip install -r requirements-backend.txt -q
    pip install -r requirements-frontend.txt -q
    pip install aiosqlite -q
    echo done > venv\installed.flag
) else (
    echo [2/5] Dependencies already installed. Skipping.
)

set ENVIRONMENT=dev
set NODE_PRESERVE_SYMLINKS=1
set DATABASE_URL=sqlite+aiosqlite:///./data/suspensionlab.db
set API_BASE_URL=http://localhost:8000
set STRIPE_PUBLIC_KEY=pk_test_placeholder
set STRIPE_SECRET_KEY=sk_test_placeholder
set PYTHONPATH=%cd%\src

if not exist "data" mkdir data

echo [3/5] Note: If ports 8000 or 8501 are already in use, you may need to free them manually.
:: Removed aggressive taskkill to prevent killing unrelated user processes.

echo [4/5] Starting Backend Server...
start /b cmd /c "venv\Scripts\uvicorn.exe suspensionlab.backend.api.main:app --host 0.0.0.0 --port 8000 > backend.log 2>&1"

echo [5/5] Waiting for backend to initialize...
:wait_loop
curl -s http://localhost:8000/health > NUL
if %ERRORLEVEL% NEQ 0 (
    timeout /t 2 /nobreak > NUL
    goto wait_loop
)

echo.
echo SuspensionLab Backend is now running on port 8000! 
echo Keep this window open. Close it to stop the server.
echo.
echo Starting Next.js Frontend...
cd frontend
npm run dev
