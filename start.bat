@echo off
chcp 65001 >nul
echo ============================================
echo   YYS Automation - Desktop Application
echo ============================================
echo.

cd /d "%~dp0"

set CONDA_ENV=D:\Users\ASUS\anaconda3\envs\timeocr
set CONDA_PYTHON=%CONDA_ENV%\python.exe
set CONDA_PIP=%CONDA_ENV%\Scripts\pip.exe

REM Check if conda env exists
if not exist "%CONDA_PYTHON%" (
    echo [ERROR] Conda env 'timeocr' not found at %CONDA_ENV%
    echo Run: conda create -n timeocr python=3.10
    pause
    exit /b 1
)

REM Install Python dependencies
echo [INFO] Installing Python dependencies...
"%CONDA_PIP%" install -r requirements.txt -q

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
