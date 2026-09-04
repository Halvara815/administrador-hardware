@echo off
setlocal
cd /d "%~dp0"
py scripts\build.py
if errorlevel 1 pause
