@echo off
setlocal EnableExtensions EnableDelayedExpansion
title MeetPilot AI
cd /d "%~dp0"

echo.
echo  MeetPilot AI - local start
echo  ==========================
echo.

REM ---- 1. Check Python 3.11+ --------------------------------------------------------------
set "PY="
where py >nul 2>&1 && (py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "PY=py -3")
if not defined PY (
  where python >nul 2>&1 && (python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "PY=python")
)
if not defined PY (
  echo [ERROR] Python 3.11 or newer was not found.
  echo         Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  goto :fail
)
for /f "delims=" %%v in ('%PY% -c "import platform; print(platform.python_version())"') do echo  [ok] Python %%v

REM ---- 2. Check Node.js 20+ ---------------------------------------------------------------
where node >nul 2>&1 || (
  echo [ERROR] Node.js was not found. Install the LTS version from https://nodejs.org/
  goto :fail
)
node -e "process.exit(Number(process.versions.node.split('.')[0]) >= 20 ? 0 : 1)" || (
  echo [ERROR] Node.js 20 or newer is required.
  goto :fail
)
for /f "delims=" %%v in ('node --version') do echo  [ok] Node.js %%v

REM ---- 3. Configuration (never overwrites an existing .env) ---------------------------------
if not exist ".env" (
  if not exist ".env.example" (
    echo [ERROR] .env.example is missing. Re-download the project.
    goto :fail
  )
  copy /y ".env.example" ".env" >nul
  for /f "delims=" %%k in ('%PY% -c "import secrets; print(secrets.token_urlsafe(48))"') do set "KEY=%%k"
  %PY% -c "import re,sys; p='.env'; s=open(p,encoding='utf-8').read(); s=re.sub(r'(?m)^SECRET_KEY=.*$', 'SECRET_KEY='+sys.argv[1], s, count=1); open(p,'w',encoding='utf-8').write(s)" "!KEY!"
  echo  [ok] Created .env from .env.example with a new SECRET_KEY
  echo       Edit .env to configure transcription and AI providers.
) else (
  echo  [ok] Using existing .env
)
findstr /r /c:"^TRANSCRIPTION_PROVIDER=none" .env >nul && echo  [info] TRANSCRIPTION_PROVIDER=none: recordings are stored but not transcribed. See INSTRUCTION.md.
findstr /r /c:"^AI_PROVIDER=none" .env >nul && echo  [info] AI_PROVIDER=none: no summaries or action items are generated. See INSTRUCTION.md.

REM ---- 4. Backend environment -------------------------------------------------------------
if not exist "backend\.venv\Scripts\python.exe" (
  echo  [..] Creating Python virtual environment
  %PY% -m venv backend\.venv || (echo [ERROR] Could not create the virtual environment. & goto :fail)
)
set "VPY=backend\.venv\Scripts\python.exe"
set "REQ=backend\requirements.txt"
findstr /r /c:"^TRANSCRIPTION_PROVIDER=local" .env >nul && set "REQ=backend\requirements-local.txt"
REM Reinstall only when the requirements file changed (its hash is kept in the virtual environment).
set "STAMP=backend\.venv\.installed-requirements"
set "HASH="
for /f "delims=" %%h in ('call "%VPY%" -c "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read()+open('backend/requirements.txt','rb').read()).hexdigest())" "%REQ%"') do set "HASH=%%h"
if not defined HASH set "HASH=unknown-%RANDOM%"
set "OLD="
if exist "%STAMP%" set /p OLD=<"%STAMP%"
if not "%OLD%"=="%HASH%" (
  echo  [..] Installing backend dependencies from %REQ% ^(first run can take a few minutes^)
  "%VPY%" -m pip install --disable-pip-version-check -q -r "%REQ%" || (echo [ERROR] pip install failed. Check your internet connection and the output above. & goto :fail)
  >"%STAMP%" echo %HASH%
)
echo  [ok] Backend dependencies installed

echo  [..] Applying database migrations
"%VPY%" -m alembic -c backend\alembic.ini upgrade head || (echo [ERROR] Database migration failed. Check DATABASE_URL in .env. & goto :fail)
echo  [ok] Database is up to date

REM ---- 5. Frontend environment ------------------------------------------------------------
if not exist "frontend\node_modules\.package-lock.json" (
  echo  [..] Installing frontend dependencies
  pushd frontend
  call npm ci --no-fund --no-audit || (popd & echo [ERROR] npm ci failed. & goto :fail)
  popd
)
echo  [ok] Frontend dependencies installed

REM ---- 6. Start services ------------------------------------------------------------------
netstat -ano | findstr /r /c:":8000 .*LISTENING" >nul && (
  echo [ERROR] Port 8000 is already in use. Close the other program or an earlier MeetPilot AI window.
  goto :fail
)
echo  [..] Starting API on http://127.0.0.1:8000 ^(includes the background job worker^)
start "MeetPilot AI - API" cmd /k ""%VPY%" -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000"
echo  [..] Starting web app on http://localhost:5173
start "MeetPilot AI - Web" cmd /k "cd /d frontend && npm run dev -- --host 127.0.0.1 --port 5173 --strictPort"

echo  [..] Waiting for the API
set /a TRIES=0
:wait
set /a TRIES+=1
"%VPY%" -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=2).status == 200 else 1)" >nul 2>&1 && goto :ready
if %TRIES% geq 60 (
  echo [ERROR] The API did not become ready within 60 seconds. Read the "MeetPilot AI - API" window for details.
  goto :fail
)
timeout /t 1 /nobreak >nul
goto :wait

:ready
echo  [ok] API is ready
timeout /t 2 /nobreak >nul
start "" "http://localhost:5173"
echo.
echo  MeetPilot AI is running at http://localhost:5173
echo  Close the "MeetPilot AI - API" and "MeetPilot AI - Web" windows to stop it.
echo  Your data stays in the data\ folder; this script never deletes it.
echo.
pause
exit /b 0

:fail
echo.
echo  Startup stopped. Nothing was deleted.
pause
exit /b 1
