# Installation and user guide

## 1. Requirements

- Python 3.11 or newer (3.12 is used in development and on Render)
- Node.js 20 or newer
- Optional: Docker Desktop, for the Docker Compose setup
- Optional: an OpenAI, Anthropic or Google Gemini API key for cloud transcription and AI analysis

## 2. Start with the scripts (recommended)

**Windows:** double-click `Start App.bat`. **macOS:** double-click `Start App.command`. If macOS blocks it, right-click it, choose **Open**, or run `chmod +x "Start App.command"` once. **Linux:** run `./"Start App.command"`.

The script:

1. checks the Python and Node.js versions and explains what to install if one is missing,
2. creates `.env` from `.env.example` with a new random `SECRET_KEY`, only if `.env` does not exist yet,
3. creates `backend/.venv` and installs the backend requirements (again only when they change),
4. applies database migrations,
5. installs the frontend packages on the first run,
6. starts the API (with the job worker) on port 8000 and the web app on port 5173, waits for the API to be ready and opens the browser.

It never deletes data. Stop the app by closing the two server windows (Windows) or pressing Ctrl+C (macOS and Linux).

## 3. Manual installation

```bash
cp .env.example .env            # then set SECRET_KEY and providers
python -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt          # Windows: backend\.venv\Scripts\pip
# add local Whisper support:  pip install -r backend/requirements-local.txt
backend/.venv/bin/python -m alembic -c backend/alembic.ini upgrade head
backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --port 8000
```

In a second terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173. The dev server proxies `/api` to port 8000. Run commands from the project root: relative paths such as `./data/meetpilot.db` are resolved from the current folder.

**Separate worker (optional):** set `EMBEDDED_WORKER=false`, then from the project root run `PYTHONPATH=backend backend/.venv/bin/python -m app.worker` (Windows: `set PYTHONPATH=backend` then `backend\.venv\Scripts\python -m app.worker`). It reads the same `.env` and must reach the same storage as the API.

**Docker:** `docker compose up --build` starts PostgreSQL, the API, a worker and the web app on http://localhost:8088 (set `WEB_PORT` to change it). The images include local Whisper with the `tiny` model.

## 4. Environment configuration

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `ENVIRONMENT` | | `development` | `production` enables strict secrets, HSTS and hides `/docs` |
| `DATABASE_URL` | production | `sqlite:///./data/meetpilot.db` | `postgresql://user:pass@host:5432/db` (`postgres://` also works) |
| `SECRET_KEY` | production | temporary key | 32+ random characters for signing tokens |
| `CORS_ORIGINS` | production | localhost:5173 | Comma-separated web app origins |
| `FRONTEND_URL` | production | `http://localhost:5173` | Used in password-reset links |
| `STORAGE_PROVIDER` | | `local` | `local` or `s3` |
| `STORAGE_ROOT` | | `./data/storage` | Folder for local storage |
| `STORAGE_PERSISTENT` | | `true` | `false` shows users a temporary-storage warning |
| `DATABASE_PERSISTENT` | | `true` | `false` warns users that accounts and data are deleted on restart (SQLite on a temporary disk) |
| `S3_BUCKET`, `S3_REGION`, `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_PREFIX` | with s3 | | Private S3-compatible bucket |
| `MAX_AUDIO_SIZE_MB` | | `200` | Upload size limit |
| `MAX_AUDIO_DURATION_MINUTES` | | `240` | Recording length limit |
| `TRANSCRIPTION_PROVIDER` | | `none` | `none`, `openai` or `local` |
| `TRANSCRIPTION_API_KEY` | openai | | OpenAI key (falls back to `OPENAI_API_KEY`) |
| `TRANSCRIPTION_MODEL` | | per provider | OpenAI: `gpt-4o-transcribe-diarize`. Local: `tiny` |
| `TRANSCRIPTION_DIARIZE`, `TRANSCRIPTION_LANGUAGE`, `TRANSCRIPTION_CHUNK_SECONDS` | | `true`, auto, `1200` | |
| `LOCAL_WHISPER_MODEL`, `LOCAL_WHISPER_MODEL_DIR`, `LOCAL_WHISPER_THREADS` | | `tiny`, cache, `2` | Local Whisper settings |
| `AI_PROVIDER` | | `none` | `none`, `openai`, `anthropic` or `gemini` |
| `AI_API_KEY`, `AI_MODEL` | with AI | | Key and model for the primary provider |
| `AI_FALLBACK_PROVIDERS` | | | For example `gemini,openai` |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` | for fallbacks | | Per-provider keys |
| `AUTO_ANALYZE` | | `true` | Analyse automatically after transcription |
| `EMBEDDED_WORKER` | | `true` | Run the job worker inside the API |
| `JOB_MAX_ATTEMPTS`, `JOB_TIMEOUT_SECONDS` | | `3`, `3600` | Retries and stale-job timeout |
| `DEMO_ENABLED` | | `true` | Public demo and demo workspaces |
| `RATE_LIMIT_ENABLED` | | `true` | |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS` | for reset emails | | Without them, reset links cannot be emailed. In development the link is printed to the API console |

Never put secrets in `VITE_` variables: they are compiled into the public web app. The only frontend variable is `VITE_API_BASE_URL`.

## 5. Database

SQLite needs no setup. For PostgreSQL, create a database, set `DATABASE_URL` and run `python -m alembic -c backend/alembic.ini upgrade head`. To create a migration after changing models: `python -m alembic -c backend/alembic.ini revision --autogenerate -m "describe change"`, then review the file.

## 6. Transcription provider setup

- **Local (free, private):** `TRANSCRIPTION_PROVIDER=local`. The start script installs `requirements-local.txt`. The `tiny` model (about 75 MB) downloads on first use. There is no speaker detection. Larger models (`base`, `small`) are more accurate but slower and use more memory.
- **OpenAI:** `TRANSCRIPTION_PROVIDER=openai` and `TRANSCRIPTION_API_KEY`. Get a key at https://platform.openai.com/api-keys. The default model separates speakers. API usage is billed by OpenAI.

Details: [TRANSCRIPTION_GUIDE.md](TRANSCRIPTION_GUIDE.md).

## 7. AI provider setup

Set `AI_PROVIDER` and `AI_API_KEY`. Keys: OpenAI https://platform.openai.com/api-keys, Anthropic https://console.anthropic.com/settings/keys, Google Gemini https://aistudio.google.com/apikey. Optional fallback: `AI_FALLBACK_PROVIDERS=gemini` plus `GEMINI_API_KEY`. **Settings → AI and transcription** shows what the server has configured. Details: [AI_ANALYSIS_GUIDE.md](AI_ANALYSIS_GUIDE.md).

## 8. Using MeetPilot AI

### Uploading recordings
**Upload Recording** → fill in the title, date, project and participants → **Continue** → choose or drop the file → **Upload and process**. The progress bar shows the real upload. Afterwards the meeting page shows the job stage, which updates automatically. You can leave the page. A meeting can also be created without audio (**Meetings → New meeting**) and filled in by hand.

If processing fails, the panel says whether **transcription** or **AI analysis** failed and why, with a retry button. A failed analysis never affects the transcript.

### Reading transcripts
Open a meeting → **Transcript**. Click a timestamp to play from there; the line being played is highlighted. Use the search box (Enter and Shift+Enter move between matches) and the speaker filter. Badges show the provider, the language, and whether timestamps and speakers are available. If they are not, the app says so instead of guessing.

### Editing transcript lines
Hover over a line → pencil → edit the text or choose another speaker → **Save**. Edited lines show an **Edited** badge, the original machine text and a **Revert** button.

### Naming speakers
**Speakers** → type a name next to each "Speaker N" → click away to save. Names only come from you; voices are never used to identify people. When a long recording was split, give the same name to speakers who are the same person.

### Reviewing summaries
**Summary** shows the executive summary, discussion points, key dates (interpreted dates are marked "confirm"), open questions, risks and suggested follow-up. **source** jumps to the supporting transcript lines. **Grounding checks** lists what MeetPilot AI removed or corrected in the AI output.

### Managing action items
Use a meeting's **Action items** tab or the **Action Items** page. Click the circle to move a task through To do, In progress and Completed. The pencil edits the task, owner, deadline, priority, status, notes and the "needs confirmation" flag. Filter by status, Overdue, Unassigned, owner, project or text. **Deadlines (.ics)** downloads a calendar file you can import yourself.

### Decisions
**Decisions** lists each decision with its status in the meeting (confirmed, proposed or uncertain) and your review (Confirm, Reject or Reset). Rejected decisions are hidden by default and excluded from counts.

### Searching meetings
Use the search bar at the top for everything, the **Transcripts** page for spoken words, or the filters on **Meetings**.

### AI assistant
**AI Assistant**, or **Ask about this meeting** on a meeting page. Answers cite sources such as `[S2]` (transcript), `[M1]` (meeting summary), `[A3]` (action item) and `[D1]` (decision); click one to open it. Without an AI provider the assistant lists the matching records instead.

### Exporting reports
A meeting's **Reports & export** tab, or the **Reports** page: generate a PDF or HTML report (optionally with the full transcript), and download the transcript (TXT, SRT, VTT, JSON), summary (Markdown, JSON), action items (CSV, Markdown, ICS) or decisions (CSV, Markdown).

### Workspaces, members and retention
**Settings → Workspaces:** rename the workspace, set a retention period (audio older than N days is deleted automatically and transcripts are kept), add members by email (they need an account), change roles, leave, or delete the workspace.

### Deleting data
Meeting **Details** → **Delete meeting**, or **Delete audio only**. **Settings → Account and data** deletes your account.

## 9. Troubleshooting

| Problem | Fix |
|---|---|
| "Python 3.11 or newer was not found" | Install Python from python.org and tick "Add python.exe to PATH" |
| "Port 8000 is already in use" | Close the other program, or an earlier MeetPilot AI window |
| Uploads stay "Uploaded" | No transcription provider is configured. Set `TRANSCRIPTION_PROVIDER` |
| "Transcription completed" but no summary | No AI provider is configured, or `AUTO_ANALYZE=false`. Use **Analyse with AI** |
| "The transcription provider rejected the API key" | Check `TRANSCRIPTION_API_KEY` and restart the API |
| "is ... audio but its name ends in ..." | The extension does not match the content. Rename the file |
| "The audio file appears to be damaged" | Re-export the recording, for example as MP3 or WAV |
| Local model cannot be loaded | The first run needs internet access to download the model. Check `LOCAL_WHISPER_MODEL_DIR` |
| Long OpenAI recording fails with "part ... still too large" | Lower `TRANSCRIPTION_CHUNK_SECONDS` |
| Signed out after a restart | `SECRET_KEY` is empty, so a temporary key is used. Set it in `.env` |
| Password reset email never arrives | Configure `SMTP_*`. In development the link is printed in the API window |
| Playback says the link expired | Reload the page; playback links last 15 minutes |
| Browser shows CORS errors | Add the web app's exact origin to `CORS_ORIGINS` |
