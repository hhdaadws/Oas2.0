@echo off
chcp 65001 >nul
echo ============================================
echo   YYS Automation - Desktop Application
echo ============================================
echo.

cd /d "%~dp0"

REM Check if venv exists
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Python venv not found. Run: python -m venv venv
    echo Then: venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

REM Install Python dependencies
echo [INFO] Installing Python dependencies...
venv\Scripts\pip install -r requirements.txt -q

REM Check if frontend node_modules exists
if not exist "frontend\node_modules" (
    echo [INFO] Installing frontend dependencies...
    cd frontend
    call npm install
    cd ..
)

REM Check if desktop node_modules exists
if not exist "desktop\node_modules" (
    echo [INFO] Installing desktop dependencies...
    cd desktop
    call npm install
    cd ..
)

echo [INFO] Starting desktop application...
cd desktop
call npx electron .
