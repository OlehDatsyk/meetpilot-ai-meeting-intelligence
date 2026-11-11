# Testing

Everything below was run on 2026-11-11 on Windows 11 with Python 3.12.10 and Node.js 24.20.0, unless stated otherwise.

## Commands

```bash
# Backend (from backend/)
python -m pytest                                    # SQLite, a fresh database per test
TEST_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/db python -m pytest   # PostgreSQL (drops and recreates tables)

# Frontend (from frontend/)
npm run typecheck
npm test
npm run build
```

## Results

| Suite | Result |
|---|---|
| Backend, SQLite (`pytest -W error::DeprecationWarning`) | **85 passed** |
| Backend, PostgreSQL 16 (Docker), migration-diff test excluded because it uses its own SQLite file | **84 passed** |
| Alembic `upgrade head` and `downgrade base` on PostgreSQL 16 | Passed |
| Frontend type-check (`tsc -b`, strict) | Passed |
| Frontend unit tests (Vitest) | **8 passed** |
| Frontend production build | Passed |
| `npm audit` | 0 vulnerabilities |
| `pip-audit` (requirements-local.txt and requirements-dev.txt) | No known vulnerabilities |
| `ruff` (pyflakes and bugbear rules) | No findings |

## What the automated tests cover

| Area | Tests |
|---|---|
| Authentication | Registration, sign-in, Argon2 hashing, same error for unknown emails and wrong passwords, protected routes, sign-out revocation, password change, reset flow (single use, no enumeration), login rate limit, account deletion, production secret check |
| Permissions and workspace isolation | A second user gets 404 on another user's meeting, transcript, summary, recording link, report, export, jobs, segment edit, action item edit, delete, upload, list, search and assistant conversation. Viewer is read-only. Last owner is protected. Cross-workspace projects are rejected. Playback tokens stop working when membership is removed |
| Audio upload and validation | Real MP3, FLAC, OGG, M4A and AAC files made with ffmpeg are detected and parsed. WAV metadata. Text renamed to audio, HTML disguised as MP3, broken WAV and extension mismatches are rejected. Empty, oversized and too-long uploads. Nothing is stored on failure. Duplicate detection, replace, and HTTP range streaming |
| Transcription jobs | Segments and speakers are saved. Conversion plus splitting into 3 parts with correct timestamp offsets and per-part speaker IDs. Providers without timestamps get none (and SRT export is refused). Retryable failures are re-queued with back-off until attempts run out. Non-retryable failures. Cancellation. Duplicate job prevention. Stale job recovery. 503 when no provider |
| OpenAI transcription adapter | Request shape for diarisation and text-only models, response parsing, error mapping (401, 429, 500, 400, connection error), and that the status endpoint never returns keys. Uses the real OpenAI SDK against a mocked HTTP transport |
| AI analysis | Grounding rules (uncited items dropped, owners and deadlines not in the cited lines removed, relative dates marked interpreted, AI vs stated priority), strict schema shape, windowing and merging, the end-to-end pipeline, user edits surviving re-analysis, failures reported as `analysis` with the transcript intact, 503 without AI, fallback to a second provider, invalid output rejected, settings registry |
| AI adapters | OpenAI (structured output request), Anthropic (request body, beta fallback header, refusal and auth error handling, using the real SDK with a mocked transport), Gemini (config passed to the SDK, with a mocked client) |
| Transcript and speakers | Editing keeps the original, revert, edit timestamps, renaming keeps the provider label, reassigning, cross-meeting speakers rejected |
| Action items and decisions | CRUD, filters (unassigned, overdue, status, text), sorting, completion time, review workflow |
| Search and assistant | Search across segments, meetings, projects, actions and decisions, with LIKE wildcards escaped. Assistant citations (unknown labels ignored), retrieval-only mode, no-results mode, conversation privacy and workspace isolation |
| Reports and exports | PDF and HTML generation, HTML escaping (XSS), sandbox CSP, CSV formula-injection guard, SRT, VTT, JSON, Markdown and ICS, PDF with Cyrillic and Japanese text |
| Deletion and storage | Meeting deletion removes files and all derived rows, and scrubs assistant answers. Audio-only deletion. Workspace and account deletion remove files. Retention sweep. Local storage path-traversal protection. S3 storage against moto (upload, download to a temporary file and cleanup, pre-signed URL, delete) |
| Dashboard and analytics | Figures match the stored records. Success rate is `null` when no jobs have finished |
| Demo | Public demo payload (every demo action cites existing demo lines), demo report, demo workspace created once, PDF from demo data |
| Migrations | `alembic upgrade head` produces exactly the models' schema |
| Frontend | Formatting, "Unassigned" and "No deadline specified" labels, AI suggestion and interpreted-date labels, multi-term highlighting with regex escaping, API error and network error handling |

## Mocked versus live provider tests

| Integration | Automated tests | Live test |
|---|---|---|
| Local transcription (faster-whisper `tiny`) | Indirectly through the job pipeline with fake providers | **Live, passed:** a 30-second, two-voice English clip (made with Windows text-to-speech, not committed) was transcribed accurately with timestamps and language "en". Run directly, through the API job queue (local dev server), and through Docker Compose with a separate worker container and PostgreSQL |
| OpenAI speech-to-text | Mocked HTTP transport | **Not tested live** (no API key available) |
| OpenAI, Anthropic, Gemini analysis and assistant | Mocked transport or client | **Not tested live** (no API keys available) |
| S3 storage | moto (in-memory AWS) | Not tested against a real bucket |
| SMTP password-reset email | Not tested | Not tested |

## Manual checks (local, development build)

- Registered through the UI. The validation message names the field (found and fixed: it used to show only "Some fields are invalid").
- Uploaded audio, watched the job states, and viewed the transcript. Clicking a timestamp seeks the audio (HTTP 206 responses) and highlights the active line.
- Opened every page of the app with the demo workspace (overview, meetings, upload, transcripts, action items, decisions, projects, assistant, reports, analytics, settings, search, 404) with no error messages.
- Asked the assistant a question without an AI key and got matching records with source links.
- `Start App.bat`: ran with port 8000 already in use. It checked the tools, installed dependencies, migrated, and then stopped with a clear message (found and fixed a quoting bug in the reinstall check). The full start that opens the browser was not run during testing. `Start App.command` was not run (no macOS machine).
- Production mode against PostgreSQL with a `postgres://` URL: `/health`, `/health/ready`, `/docs` returning 404, CORS allowing the configured origin and rejecting others, HSTS, registration.
- Docker Compose: all images build, and the stack transcribed an upload end to end.
- Memory: the API process with the embedded worker peaked at about 230 MB while transcribing with `tiny` (Windows measurement).

## Known issues and untested features

- The live OpenAI, Anthropic and Gemini paths are unverified (see above).
- No browser end-to-end test suite. UI checks were manual.
- Rate limiting is tested for sign-in only. The other limits use the same mechanism.
- Concurrent workers are designed for (conditional claim) but were not load-tested.
- `Start App.command` was not run on macOS.
