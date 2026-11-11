@echo off
REM Development API server (used by the preview tooling; "Start App.bat" is the normal way to run the app).
cd /d "%~dp0.."
"backend\.venv\Scripts\python.exe" -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
