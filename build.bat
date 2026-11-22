@echo off
setlocal
echo ===================================================
echo   DZ Car Rental Finder - Windows Executable Build
echo ===================================================

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found. Run setup.bat first.
    pause
    exit /b 1
)

where npm >nul 2>&1
if %errorlevel% equ 0 (
    echo Building frontend production bundle...
    call npm run build
    if %errorlevel% neq 0 exit /b 1
)

if not exist "dist\index.html" (
    echo [ERROR] dist\index.html missing. Build the frontend before packaging.
    pause
    exit /b 1
)

echo Running automated backend tests before packaging...
set PYTHONPATH=backend
.venv\Scripts\pytest.exe backend\tests
if %errorlevel% neq 0 (
    echo [ERROR] Tests failed. Fix issues before building executable.
    pause
    exit /b 1
)

echo Packaging with PyInstaller...
.venv\Scripts\pyinstaller.exe ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --name "DZCarRentalFinder" ^
  --distpath "dist_win" ^
  --workpath "build_win" ^
  --add-data "dist;dist" ^
  --add-data "data\boundaries;data\boundaries" ^
  --add-data "backend\app;backend\app" ^
  --hidden-import "uvicorn.logging" ^
  --hidden-import "uvicorn.loops.auto" ^
  --hidden-import "uvicorn.protocols.http.auto" ^
  --hidden-import "uvicorn.lifespan.on" ^
  desktop\launcher.py

if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller build failed.
    pause
    exit /b 1
)

echo.
echo Build succeeded: dist_win\DZCarRentalFinder\DZCarRentalFinder.exe
pause
