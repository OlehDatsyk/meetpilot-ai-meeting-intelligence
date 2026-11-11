# API documentation

Every endpoint listed here is implemented. In development, interactive OpenAPI docs are at `http://127.0.0.1:8000/docs`; they are turned off in production.

## Conventions

- Base path: `/api/v1`. Health checks are at `/health` and `/health/ready`.
- **Authentication:** `Authorization: Bearer <access_token>` from `/auth/register` or `/auth/login`. Tokens last `ACCESS_TOKEN_MINUTES` (default 12 hours). Signing out, changing the password and resetting it revoke every earlier token.
- **Authorisation:** checked on every request. A record in a workspace you do not belong to returns **404**, so its existence is not revealed. Roles: `viewer` (read only), `member` (create and edit), `admin` (workspace settings and members), `owner` (everything, including deletion).
- **Workspace scope:** list endpoints take `workspace_id` as a query parameter. Item endpoints find the workspace from the item.
- **Pagination:** `page` (from 1) and `page_size`. Responses are `{"items": [...], "total": n, "page": p, "page_size": s}`.
- **Times** are ISO 8601 in UTC. Dates (`due_date`) are `YYYY-MM-DD`.
- **Errors:** `{"error": {"code": "...", "message": "...", "details": ...}}`. Validation errors (`422`, `validation_error`) list `details` as `[{"field", "message"}]`.

| Status | Meaning |
|---|---|
| 400 | Invalid request (`bad_request`, `no_transcript`, `last_owner`, ...) |
| 401 | Missing or expired token (`unauthorized`), bad sign-in (`invalid_credentials`) |
| 403 | Your role does not allow this (`forbidden`) |
| 404 | Not found, or not visible to you |
| 409 | Conflict (`email_taken`, `job_in_progress`, `recording_exists`, `already_member`) |
| 410 | Audio or report file no longer stored (`audio_deleted`, `report_missing`) |
| 413 | Upload too large or too long (`file_too_large`, `too_long`) |
| 415 | Not a supported audio file (`unsupported_format`, `unrecognised_content`, `extension_mismatch`) |
| 422 | Validation failed, or the audio is damaged (`malformed_audio`) |
| 429 | Rate limited (`rate_limited`, with `Retry-After`) |
| 502 | The AI provider failed while answering an assistant question |
| 503 | Transcription or AI provider not configured |

## Rate limits

Per client IP, per API process: register 5/hour, login 10/5 min, password-reset request 5/15 min, upload 20/hour, analysis 30/hour, reports 30/hour, assistant 40/hour, search 120/min.

## Health

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | Liveness. `{"status":"ok","version":"1.0.0"}`. Touches nothing else |
| GET | `/health/ready` | Database and storage check. `200 {"status":"ready","database":"ok","storage":"ok"}` or `503`. Never calls a provider |

## Auth

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/auth/register` | `{email, password (10+ chars), name}` | `201` token + user. Creates a personal workspace |
| POST | `/auth/login` | `{email, password}` | token + user |
| POST | `/auth/logout` | | Revokes all tokens for the user |
| GET | `/auth/me` | | user |
| PATCH | `/auth/me` | `{name}` | user |
| POST | `/auth/change-password` | `{current_password, new_password}` | new token |
| POST | `/auth/password-reset/request` | `{email}` | Always the same message. Emails a link when SMTP is configured |
| POST | `/auth/password-reset/confirm` | `{token, new_password}` | Single-use, expires after `PASSWORD_RESET_MINUTES` |
| DELETE | `/auth/me` | `{password}` | Deletes the account and workspaces where the user is the only owner |

```http
POST /api/v1/auth/login
{"email": "maya@example.com", "password": "correct-horse-1"}

200 {"access_token": "eyJ...", "token_type": "bearer", "expires_in": 43200,
     "user": {"id": "3f...", "email": "maya@example.com", "name": "Maya Chen", "created_at": "..."}}
```

## Workspaces

| Method | Path | Notes |
|---|---|---|
| GET | `/workspaces` | Your workspaces with your role |
| POST | `/workspaces` | `{name}` |
| PATCH | `/workspaces/{id}` | admin: `{name?, recording_retention_days? (1-3650), clear_retention?}` |
| DELETE | `/workspaces/{id}` | owner. Deletes all data and files. Not allowed for your only workspace |
| GET | `/workspaces/{id}/members` | |
| POST | `/workspaces/{id}/members` | admin: `{email, role}`. The person must already have an account |
| PATCH | `/workspaces/{id}/members/{member_id}` | admin (owner to grant or change owner): `{role}` |
| DELETE | `/workspaces/{id}/members/{member_id}` | admin, or yourself to leave. The last owner cannot be removed |
| GET | `/workspaces/{id}/activity?limit=30` | Activity log (no transcript content) |

## Projects

| Method | Path | Notes |
|---|---|---|
| GET | `/projects?workspace_id=` | With meeting, decision and action counts |
| POST | `/projects` | member: `{workspace_id, name, description}` |
| GET / PATCH | `/projects/{id}` | |
| DELETE | `/projects/{id}` | admin. Meetings are kept without a project |

## Meetings, uploads and jobs

| Method | Path | Notes |
|---|---|---|
| GET | `/meetings?workspace_id=&q=&project_id=&status=&date_from=&date_to=&sort=&page=&page_size=` | `project_id=none` for meetings without one. `status` takes comma-separated values. `sort`: `date_desc`, `date_asc`, `title_asc`, `title_desc` |
| POST | `/meetings` | `{workspace_id, title, description?, meeting_date?, duration_minutes?, project_id?, participants?: [{name, email?, role?}]}` |
| GET | `/meetings/{id}` | Includes `recording`, `latest_job` and `transcript_info` |
| PATCH | `/meetings/{id}` | Any of the create fields, `clear_project` |
| DELETE | `/meetings/{id}` | Deletes the recording, transcript, analysis, reports and assistant answers that cite it |
| POST | `/meetings/{id}/recording` | `multipart/form-data`: `file`, `replace` (bool), `auto_transcribe` (bool, default true) |
| POST | `/meetings/{id}/transcribe` | `202` job. `503` when no transcription provider |
| POST | `/meetings/{id}/analyze` | `202` job. `503` when no AI provider |
| GET | `/meetings/{id}/jobs` | Last 20 jobs |
| GET | `/jobs/{id}` | |
| POST | `/jobs/{id}/cancel` | Queued jobs stop at once; running jobs stop after the current step |

Upload response:

```json
{"meeting": {"id": "...", "status": "queued", "recording": {"audio_format": "mp3", "duration_seconds": 1834.2, "...": "..."}},
 "job": {"id": "...", "kind": "transcription", "status": "queued", "stage": "Waiting for a worker"},
 "duplicate_of": [{"meeting_id": "...", "title": "Same file uploaded here before"}],
 "notice": null}
```

Meeting `status` values: `draft`, `uploaded`, `queued`, `transcribing`, `transcribed`, `analysing`, `completed`, `failed`, `cancelled`. When `failed`, `error_stage` is `transcription` or `analysis` and `error_message` is safe to display. Job `stage`, `progress_current` and `progress_total` report real progress, for example `"Transcribing part 2 of 3"`.

## Recordings

| Method | Path | Notes |
|---|---|---|
| GET | `/recordings/{id}/media-url` | `{"url", "absolute", "expires_in": 900}`. A 15-minute signed link (or an S3 pre-signed URL) |
| GET | `/media/{token}` | Streams audio with HTTP range support. The token is bound to the recording and user, and membership is re-checked |
| DELETE | `/recordings/{id}/audio` | Deletes the audio file and keeps the transcript and analysis |

## Transcripts

| Method | Path | Notes |
|---|---|---|
| GET | `/meetings/{id}/transcript` | Provider, model, language, `has_timestamps`, `has_diarization`, speakers and segments |
| PATCH | `/segments/{id}` | `{text}` to edit, `{speaker_id}` to reassign, `{revert: true}` to restore the machine text. `original_text` never changes |
| PATCH | `/speakers/{id}` | `{display_name}`. Empty clears it. The provider's `label` never changes |

Segment example:

```json
{"id": "...", "position": 7, "start_seconds": 41.2, "end_seconds": 46.8, "speaker_id": "...",
 "speaker_name": "Speaker 2", "text": "I'll send the designs by Friday.",
 "original_text": "I'll send the designs by Friday.", "edited": false, "edited_at": null}
```

## Analysis

| Method | Path | Notes |
|---|---|---|
| GET | `/meetings/{id}/summary` | Summary sections, each with `segment_ids`, plus `grounding_notes`, provider and model |
| GET | `/decisions?workspace_id=&meeting_id=&project_id=&meeting_status=&review_status=&q=` | |
| POST | `/decisions` | `{meeting_id, title, description?, meeting_status?, participants?}` |
| PATCH / DELETE | `/decisions/{id}` | `review_status`: `unreviewed`, `confirmed`, `rejected` |
| GET | `/action-items?workspace_id=&meeting_id=&project_id=&status=&owner=&overdue=&has_due_date=&q=&sort=` | `owner=unassigned` for items without an owner. `sort`: `due_asc`, `priority`, `created_desc` |
| POST | `/action-items` | `{meeting_id, title, description?, owner?, due_date?, priority?, notes?}` |
| PATCH | `/action-items/{id}` | Any field, plus `clear_owner`, `clear_due_date`, `clear_priority`, `status`, `needs_confirmation` |
| DELETE | `/action-items/{id}` | |

Action item fields that explain where a value came from: `owner_source` (`transcript` or `user`), `due_source` (`transcript`, `ai_interpreted` or `user`), `due_text` (the words used in the meeting), `priority_source` (`stated`, `ai_suggested` or `user`), `needs_confirmation`, `source_segment_ids` and `excerpt`.

## Assistant

| Method | Path | Notes |
|---|---|---|
| GET | `/assistant/conversations?workspace_id=` | Only your own conversations |
| POST | `/assistant/conversations` | `{workspace_id, meeting_id?}`. `meeting_id` limits answers to that meeting |
| GET / DELETE | `/assistant/conversations/{id}` | |
| POST | `/assistant/conversations/{id}/messages` | `{content, project_id?}`. Returns `[question, answer]` |

Answer `mode`: `ai` (written by the AI from the sources), `retrieval_only` (no AI provider configured, matching records listed), or `no_results` (nothing relevant found, so the AI is not called). `citations` holds the sources the answer cites: `{label: "S2", type: "segment", meeting_id, meeting_title, meeting_date, segment_id, start_seconds, speaker, excerpt}`.

## Search

`GET /search?workspace_id=&q=&limit=10` returns `meetings`, `segments` (ranked transcript passages), `action_items`, `decisions` and `projects`, plus the `terms` used. Keyword matching only.

## Reports and exports

| Method | Path | Notes |
|---|---|---|
| POST | `/meetings/{id}/reports` | `{format: "pdf" or "html", include_transcript}`. Stored privately |
| GET | `/reports?workspace_id=&meeting_id=` | |
| GET | `/reports/{id}/download` | Attachment. HTML is served with a `sandbox` Content-Security-Policy |
| DELETE | `/reports/{id}` | |
| GET | `/meetings/{id}/export/transcript?format=txt\|srt\|vtt\|json` | SRT and VTT need timestamps |
| GET | `/meetings/{id}/export/summary?format=md\|json` | |
| GET | `/meetings/{id}/export/report?format=pdf\|html&include_transcript=` | Generated on the fly, not stored |
| GET | `/meetings/{id}/export/action-items?format=csv\|md\|ics` | ICS holds all-day events for items with deadlines |
| GET | `/meetings/{id}/export/decisions?format=csv\|md` | |
| GET | `/exports/action-items?workspace_id=&format=csv\|md\|ics` | Whole workspace |
| GET | `/exports/decisions?workspace_id=&format=csv\|md` | Whole workspace |

CSV cells that start with `=`, `+`, `-` or `@` are prefixed with `'` to stop spreadsheet formula injection.

## Dashboard and analytics

- `GET /dashboard?workspace_id=`: stats, recent meetings, upcoming deadlines, recent activity, meetings per week (8 weeks).
- `GET /analytics?workspace_id=&weeks=12`: totals, processing success rate, decisions by project, action status counts and weekly series (4 to 52 weeks).

## System and demo

- `GET /system/config` (public): `demo_enabled`, `password_reset_email`, `version`.
- `GET /system/status` (signed in): which transcription and AI providers are configured, storage, upload limits. Never returns keys.
- `GET /demo` (public): fictional demo meetings. `GET /demo/report.html` (public): the demo report.
- `POST /demo/workspace`: creates, once, a demo workspace for the signed-in user. Returns its id in `message`.
