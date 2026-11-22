@echo off
setlocal
set PYTHONPATH=backend
.venv\Scripts\pytest.exe -v backend\tests
pause
