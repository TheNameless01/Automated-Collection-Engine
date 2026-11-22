@echo off
setlocal
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found. Run setup.bat first.
    pause
    exit /b 1
)

echo Starting DZ Car Rental Finder...
.venv\Scripts\python.exe desktop\launcher.py %*
if %errorlevel% neq 0 (
    echo [ERROR] Application exited with code %errorlevel%.
    pause
)
