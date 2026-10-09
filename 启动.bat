@echo off
cd /d "%~dp0"
python -u app.py
if errorlevel 1 pause
