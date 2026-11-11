# Deploying to Render

## Live deployment (2026-11-11)

| | |
|---|---|
| Web app | https://meetpilot-frontend.onrender.com |
| API | https://meetpilot-api-mk2h.onrender.com (Render added the `-mk2h` suffix because the plain name was taken) |
| Health | https://meetpilot-api-mk2h.onrender.com/health and `/health/ready` |
| Services | `meetpilot-api` (free web service), `meetpilot-frontend` (static site), created from Blueprint `meetpilot-ai` |
| Auto-deploy | On every push to `main` |

**Verified live:**
- `/health` and `/health/ready` (database and storage OK).
- `/docs` and `/openapi.json` return 404.
- CORS allows only the web app's origin.
- HSTS and the security headers are set on the API and the static site.
- Protected endpoints return 401 without a valid token. Forged tokens and bad media tokens are rejected.
- Registration validation errors are returned.
- The public demo API and the sandboxed demo report work.
- Every web route loads, including direct links to client-side routes.
- The bundle points at the live API, with no `localhost` URLs and no secrets.
- The demo page renders from the live API with no console errors.
- The temporary-data warning shows on registration.

**Signed-in flows** (registration, sign-in, upload, transcription, reports, deletion) were tested on the live site by the repository owner, who reported that everything works. They were not independently checked against the server logs. The same flows also pass locally, in Docker Compose and in the automated tests. After deployment, the owner set `AI_PROVIDER` and `AI_API_KEY` on `meetpilot-api` in the dashboard and reported that AI summaries work on the live site. The key is stored only in Render and never in the repository.

Two problems were found and fixed during deployment:
- Render applies service environment variables during the build, so `HF_HUB_OFFLINE=1` blocked the model download. The build command now sets `HF_HUB_OFFLINE=0`.
- The static site's `VITE_API_BASE_URL` had to be changed to the suffixed API URL.

Render facts were checked against the [Blueprint specification](https://render.com/docs/blueprint-spec) on 2026-11-11. Plans and prices change, so check [render.com/pricing](https://render.com/pricing) before creating anything.

## Architecture

| Component | Render type | Name | Plan in `render.yaml` |
|---|---|---|---|
| Web app (React) | Static Site | `meetpilot-frontend` | Free (static sites are free) |
| API + embedded job worker + local Whisper + SQLite | Python Web Service | `meetpilot-api` | `free` |
| PostgreSQL | not created | | A workspace can have only one free Postgres database, and this one already has one. The smallest paid instance, `0.1c-256mb`, cost $6/month plus $0.30/GB storage on 2026-11-11 |
| Separate worker | Background Worker | not created | Workers have no free plan |
| Persistent audio storage | Disk or S3 | not created | Disks require a paid service |

The API uses the `frankfurt` region. Change `region` in `render.yaml` before the first deployment if you prefer another one; it cannot be changed afterwards.

## Free plan limitations

| Limit | Effect |
|---|---|
| No persistent disk on free web services | **The SQLite database, uploaded audio and report files live on the temporary disk, so accounts and all data are deleted on restart, redeploy or sleep.** `DATABASE_PERSISTENT=false` shows every user a warning on the sign-in and registration pages and inside the app |
| Sleeps after 15 minutes without traffic | The first request afterwards takes about a minute. A job that was running is recovered after `JOB_TIMEOUT_SECONDS` |
| 512 MB RAM, shared CPU | Local Whisper `tiny` with one thread. About 230 MB peak was measured on Windows; Render's Linux figures will differ. Expect transcription to take longer than real time on a shared CPU |
| 750 free instance hours per month | Shared across the workspace |

The Blueprint therefore sets `MAX_AUDIO_SIZE_MB=50` and `MAX_AUDIO_DURATION_MINUTES=60`. This setup is a public demonstration, not a place to keep real recordings. The public demo page (`/demo`) does not depend on stored data, so it always works.

## Commands (as in `render.yaml`)

API (`rootDir: backend`):

```bash
# build
pip install --disable-pip-version-check -r requirements-local.txt && HF_HUB_OFFLINE=0 python scripts/download_whisper_model.py tiny ./models
# start (migrations run here because preDeployCommand is paid-only)
python -m alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*' --timeout-graceful-shutdown 20
```

Health check path: `/health` (liveness, no database or provider calls). `/health/ready` also checks the database and storage.

Static site:

```bash
cd frontend && npm ci --include=dev --no-fund --no-audit && npm run build     # publishes frontend/dist
```

A rewrite of `/*` to `/index.html` makes direct links work. Security headers and a Content-Security-Policy are set in the Blueprint.

## Environment variables

| Service | Variable | Value |
|---|---|---|
| API | `DATABASE_URL`, `DATABASE_PERSISTENT` | `sqlite:////tmp/meetpilot/meetpilot.db`, `false` |
| API | `SECRET_KEY` | Generated by Render |
| API | `CORS_ORIGINS`, `FRONTEND_URL` | Prompted: the static site URL, for example `https://meetpilot-frontend.onrender.com` |
| API | `ENVIRONMENT=production`, `STORAGE_ROOT=/tmp/meetpilot`, `STORAGE_PERSISTENT=false`, `TRANSCRIPTION_PROVIDER=local`, `LOCAL_WHISPER_MODEL=tiny`, `LOCAL_WHISPER_MODEL_DIR=./models`, `LOCAL_WHISPER_THREADS=1`, `HF_HUB_OFFLINE=1`, `EMBEDDED_WORKER=true` | Fixed |
| API | `AI_PROVIDER`, `AI_API_KEY` | `none` in the Blueprint. On the live site, set by the owner in the dashboard |
| Static site | `VITE_API_BASE_URL` | Prompted: the API URL, for example `https://meetpilot-api.onrender.com` |

Optional, set in the dashboard: `AI_PROVIDER` (`openai`, `anthropic` or `gemini`) with `AI_API_KEY`, or `TRANSCRIPTION_PROVIDER=openai` with `TRANSCRIPTION_API_KEY` (for speaker diarisation), plus `SMTP_*` for password-reset emails. Never put keys in the static site's variables.

## Deployment steps

1. Sign in at https://dashboard.render.com and connect the GitHub account that owns the repository.
2. **New → Blueprint**, select `meetpilot-ai-meeting-intelligence`, branch `main`.
3. Enter the prompted values. If the suggested names are taken, Render adds a suffix, so use the real URLs shown by Render.
4. **Apply.** The API build installs dependencies and downloads the Whisper model (several minutes).
5. Check `https://<api>/health/ready` for `{"status":"ready","database":"ok","storage":"ok"}`, then open the static site and register.

If a URL was entered wrong, fix `CORS_ORIGINS` or `FRONTEND_URL` on the API (restart) or `VITE_API_BASE_URL` on the static site (needs a rebuild, because Vite variables are compiled in).

## Continuous deployment

Both services use `autoDeployTrigger: commit` on `main`: every push to `main` redeploys. Other branches are not deployed. Migrations run on every API start; they are additive, and nothing resets the database.

## Moving to persistent storage (paid)

- **Database:** create a Render Postgres instance (or uncomment the `databases` block in `render.yaml`), set `DATABASE_URL` to its internal connection string, and set `DATABASE_PERSISTENT=true`. Migrations run at the next start.

- **S3-compatible bucket (recommended):** set `STORAGE_PROVIDER=s3`, `S3_BUCKET`, `S3_REGION` and keys (plus `S3_ENDPOINT_URL` for R2, B2 or MinIO), and `STORAGE_PERSISTENT=true`. Keep the bucket private. Add the bucket's domain to the static site CSP `media-src` for playback. This also allows a separate worker service.
- **Render disk:** needs a paid web service. Mount it at for example `/var/data`, set `STORAGE_ROOT=/var/data/storage` and `STORAGE_PERSISTENT=true`. A disk attaches to one service, so keep `EMBEDDED_WORKER=true`.
- **Separate worker:** a paid Background Worker running `python -m app.worker` with the same environment, `EMBEDDED_WORKER=false` on the API, and S3 storage.

## Troubleshooting

| Symptom | Check |
|---|---|
| Build fails at `download_whisper_model.py` | The Hugging Face Hub was unreachable during the build. Redeploy |
| `RuntimeError: SECRET_KEY must be set` | The generated `SECRET_KEY` is missing. Add one with 32+ characters |
| Web app shows "Cannot reach the MeetPilot AI server" | `VITE_API_BASE_URL` is wrong. Fix it and redeploy the static site |
| Browser console shows CORS errors | `CORS_ORIGINS` must match the static site origin exactly, with `https://` and no trailing slash |
| Transcription fails with out-of-memory or restarts | Keep `tiny` and one thread, shorten recordings, or use a larger plan or OpenAI transcription |
| Audio player says the audio is unavailable after a while | Free-plan storage was cleared on restart (expected) |
