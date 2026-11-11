#!/usr/bin/env bash
# MeetPilot AI - local start for macOS and Linux. Double-click in Finder, or run: ./"Start App.command"
set -euo pipefail
cd "$(dirname "$0")"

fail() { echo; echo "[ERROR] $*"; echo "Startup stopped. Nothing was deleted."; read -r -p "Press Enter to close." _ || true; exit 1; }
ok() { echo " [ok] $*"; }

echo
echo " MeetPilot AI - local start"
echo " =========================="

# 1. Python 3.11+
PY=""
for c in python3.13 python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then PY="$c"; break; fi
done
[ -n "$PY" ] || fail "Python 3.11 or newer was not found. Install it from https://www.python.org/downloads/"
ok "Python $($PY -c 'import platform; print(platform.python_version())')"

# 2. Node.js 20+
command -v node >/dev/null 2>&1 || fail "Node.js was not found. Install the LTS version from https://nodejs.org/"
node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 20 ? 0 : 1)' || fail "Node.js 20 or newer is required."
ok "Node.js $(node --version)"

# 3. Configuration (never overwrites an existing .env)
if [ ! -f .env ]; then
  [ -f .env.example ] || fail ".env.example is missing. Re-download the project."
  cp .env.example .env
  KEY="$($PY -c 'import secrets; print(secrets.token_urlsafe(48))')"
  $PY - "$KEY" <<'PYEOF'
import re, sys
p = ".env"
s = open(p, encoding="utf-8").read()
s = re.sub(r"(?m)^SECRET_KEY=.*$", "SECRET_KEY=" + sys.argv[1], s, count=1)
open(p, "w", encoding="utf-8").write(s)
PYEOF
  ok "Created .env from .env.example with a new SECRET_KEY (edit it to configure providers)"
else
  ok "Using existing .env"
fi
grep -q '^TRANSCRIPTION_PROVIDER=none' .env && echo " [info] TRANSCRIPTION_PROVIDER=none: recordings are stored but not transcribed. See INSTRUCTION.md."
grep -q '^AI_PROVIDER=none' .env && echo " [info] AI_PROVIDER=none: no summaries or action items are generated. See INSTRUCTION.md."

# 4. Backend
[ -x backend/.venv/bin/python ] || { echo " [..] Creating Python virtual environment"; $PY -m venv backend/.venv || fail "Could not create the virtual environment."; }
VPY=backend/.venv/bin/python
REQ=backend/requirements.txt
grep -q '^TRANSCRIPTION_PROVIDER=local' .env && REQ=backend/requirements-local.txt
STAMP="backend/.venv/.installed-$(basename "$REQ")"
if [ ! -f "$STAMP" ] || [ "$REQ" -nt "$STAMP" ]; then
  echo " [..] Installing backend dependencies from $REQ (first run can take a few minutes)"
  "$VPY" -m pip install --disable-pip-version-check -q -r "$REQ" || fail "pip install failed. Check your internet connection and the output above."
  touch "$STAMP"
fi
ok "Backend dependencies installed"
"$VPY" -m alembic -c backend/alembic.ini upgrade head || fail "Database migration failed. Check DATABASE_URL in .env."
ok "Database is up to date"

# 5. Frontend
if [ ! -f frontend/node_modules/.package-lock.json ]; then
  echo " [..] Installing frontend dependencies"
  (cd frontend && npm ci --no-fund --no-audit) || fail "npm ci failed."
fi
ok "Frontend dependencies installed"

# 6. Start
if command -v lsof >/dev/null 2>&1 && lsof -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  fail "Port 8000 is already in use. Stop the other program first."
fi
"$VPY" -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 &
API_PID=$!
(cd frontend && npm run dev -- --host 127.0.0.1 --port 5173 --strictPort) &
WEB_PID=$!
cleanup() { echo; echo " Stopping MeetPilot AI"; kill "$API_PID" "$WEB_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

for i in $(seq 1 60); do
  if "$VPY" -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=2).status == 200 else 1)" 2>/dev/null; then break; fi
  kill -0 "$API_PID" 2>/dev/null || fail "The API stopped during startup. Read the messages above."
  [ "$i" = 60 ] && fail "The API did not become ready within 60 seconds."
  sleep 1
done
ok "API is ready"
sleep 2
(command -v open >/dev/null && open http://localhost:5173) || (command -v xdg-open >/dev/null && xdg-open http://localhost:5173) || true
echo
echo " MeetPilot AI is running at http://localhost:5173"
echo " Press Ctrl+C (or close this window) to stop. Your data stays in data/; this script never deletes it."
wait
