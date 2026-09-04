@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Primero ejecute build.cmd
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m hardware_admin.main
