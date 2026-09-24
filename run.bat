@echo off
setlocal enabledelayedexpansion
title DMart SmartStock AI - Setup and Run
color 0B

echo ============================================================
echo   DMart SmartStock AI - Windows Setup and Launcher
echo   Flask backend (API) + Streamlit dashboard (frontend)
echo   (Demo using synthetic / simulated retail data)
echo ============================================================
echo.

REM Move to the folder this script lives in
cd /d "%~dp0"

REM ------------------------------------------------------------
REM 1. Create virtual environment if it doesn't exist
REM ------------------------------------------------------------
if not exist "venv\" (
    echo [1/7] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo.
        echo ERROR: Could not create a virtual environment.
        echo Make sure Python 3.10+ is installed and on your PATH.
        pause
        exit /b 1
    )
) else (
    echo [1/7] Virtual environment already exists - skipping.
)

REM ------------------------------------------------------------
REM 2. Activate virtual environment
REM ------------------------------------------------------------
echo [2/7] Activating virtual environment...
call venv\Scripts\activate.bat

REM ------------------------------------------------------------
REM 3. Install dependencies (Flask, ML stack, Streamlit, requests, plotly)
REM ------------------------------------------------------------
echo [3/7] Installing dependencies from requirements.txt...
pip install --upgrade pip >nul
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERROR: Failed to install dependencies. Check your internet connection.
    pause
    exit /b 1
)

REM ------------------------------------------------------------
REM 4. Generate synthetic dataset (only if missing)
REM ------------------------------------------------------------
if not exist "data\dmart_synthetic_sales.csv" (
    echo [4/7] Generating synthetic dataset...
    python scripts\generate_data.py
) else (
    echo [4/7] Synthetic dataset already exists - skipping generation.
)

REM ------------------------------------------------------------
REM 5. Train ML model (only if missing)
REM ------------------------------------------------------------
if not exist "models\demand_model.pkl" (
    echo [5/7] Training demand forecasting model...
    python scripts\train_model.py
) else (
    echo [5/7] Trained model already exists - skipping training.
)

REM ------------------------------------------------------------
REM 6. Initialize database (only if missing)
REM ------------------------------------------------------------
if not exist "data\dmart_smartstock.db" (
    echo [6/7] Initializing database...
    python scripts\initialize_db.py
) else (
    echo [6/7] Database already exists - skipping initialization.
)

REM ------------------------------------------------------------
REM 7. Start Flask backend (own window) + Streamlit frontend (this window)
REM ------------------------------------------------------------
echo [7/7] Starting backend and dashboard...
echo.

set FLASK_STARTED_BY_US=0
python frontend_streamlit\wait_for_backend.py --url http://127.0.0.1:5000/api/health --timeout 1 --quiet
if errorlevel 1 (
    echo Starting Flask backend in a new window...
    start "DMart SmartStock - Flask Backend" cmd /k "title DMart SmartStock - Flask Backend && call venv\Scripts\activate.bat && python backend\app.py"
    set FLASK_STARTED_BY_US=1
) else (
    echo A backend is already answering on http://127.0.0.1:5000 - reusing it.
)

echo Waiting for the backend to become ready...
python frontend_streamlit\wait_for_backend.py --url http://127.0.0.1:5000/api/health --timeout 90
if errorlevel 1 (
    echo.
    echo ERROR: The Flask backend did not start within 90 seconds.
    echo Look at the "DMart SmartStock - Flask Backend" window for the error message.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   Backend API : http://127.0.0.1:5000
echo   Dashboard   : http://localhost:8501   (opens automatically)
echo   Press CTRL+C in this window to stop the dashboard.
echo ============================================================
echo.

REM Open the browser as soon as Streamlit is answering (runs in the background)
start "DMart browser opener" /min python frontend_streamlit\wait_for_backend.py --url http://127.0.0.1:8501 --timeout 90 --quiet --open http://localhost:8501

streamlit run frontend_streamlit\app.py --server.port 8501 --server.headless true

REM ------------------------------------------------------------
REM Streamlit has exited: shut down the Flask window we opened
REM ------------------------------------------------------------
if "!FLASK_STARTED_BY_US!"=="1" (
    echo Stopping Flask backend...
    taskkill /FI "WINDOWTITLE eq DMart SmartStock - Flask Backend*" /T /F >nul 2>&1
)

pause
