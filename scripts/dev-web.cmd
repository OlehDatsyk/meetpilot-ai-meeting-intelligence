@echo off
REM Development web server with API proxy ("Start App.bat" is the normal way to run the app).
cd /d "%~dp0..\frontend"
npm run dev -- --host 127.0.0.1
