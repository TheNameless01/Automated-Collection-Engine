@echo off
setlocal enabledelayedexpansion
echo ============================================
echo   DZ Car Rental Finder - Windows Setup
echo ============================================

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python 3.11+ was not found on PATH.
    echo Install Python 3.11 or 3.12 from https://www.python.org/downloads/windows/
    echo Make sure to check "Add python.exe to PATH" during installation.
    pause
    exit /b 1
)

python -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python 3.10 or newer is required.
    python --version
    pause
    exit /b 1
)

if not exist ".venv" (
    echo Creating Python virtual environment (.venv)...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

echo Installing Python dependencies...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\pip.exe install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install Python packages.
    pause
    exit /b 1
)

echo Initializing SQLite database and 69-wilaya dataset...
.venv\Scripts\python.exe scripts\init_db.py
if %errorlevel% neq 0 (
    echo [ERROR] Database initialization failed.
    pause
    exit /b 1
)

where npm >nul 2>&1
if %errorlevel% equ 0 (
    echo Building local web dashboard...
    call npm install
    call npm run build
) else (
    if not exist "dist\index.html" (
        echo [WARN] Node.js / npm not found and dist\index.html is missing.
        echo Install Node.js LTS from https://nodejs.org/ and run "npm install && npm run build".
    )
)

echo.
echo Setup complete! Double-click run.bat to launch DZ Car Rental Finder.
pause
