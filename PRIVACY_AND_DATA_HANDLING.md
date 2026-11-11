# Privacy and data handling

MeetPilot AI processes recordings of conversations, which can be confidential. This document describes what the software does. It is not legal advice, and the project has not been reviewed or certified for GDPR or any other regulation. Whoever operates an installation is responsible for its legal basis, its processor agreements and its privacy notice. The in-app notice is at `/privacy`.

## Audio storage

- Uploaded audio is stored as a file (local disk or a private S3-compatible bucket), never in the database. The database holds the storage key, file name, format, size, duration, sample rate, channels and a SHA-256 hash.
- Files are not publicly reachable. Playback uses a 15-minute token bound to the recording and the user, and workspace membership is re-checked when the audio is streamed. With S3, 15-minute pre-signed URLs to a private bucket are used.
- Temporary copies made for conversion and splitting are deleted when the job ends, whether it succeeds or fails. Upload buffers are deleted immediately.
- On the free Render deployment, the database and all files are on the instance's temporary disk and are deleted on restart, redeploy or sleep. Users see a warning.

## Transcript storage

Transcript segments are stored in the database with the original machine text and the current (possibly edited) text, plus timestamps, speaker IDs, edit time and editor. Summaries, decisions, action items, assistant conversations and generated reports (files) are stored too. The activity log stores short descriptions such as "Transcribed “Weekly sync”", never transcript content.

## AI and transcription provider processing

| When | What is sent | To |
|---|---|---|
| Transcription, `openai` | The audio (possibly converted or split) | OpenAI |
| Transcription, `local` | Nothing leaves the server | |
| Analysis | Meeting title and date, participant names entered by users, numbered transcript text | The configured AI provider, and fallbacks if it fails |
| Assistant | The question, the user's name, recent conversation, retrieved excerpts and summaries | The configured AI provider |

MeetPilot AI does not use customer recordings or transcripts to train models. Each provider's own terms decide retention and use of API data; check them, and any data-processing agreement, before enabling a provider. Provider keys stay in server environment variables.

## Data deletion

| Action | Deletes |
|---|---|
| Delete meeting | Recording file, transcript, speakers, summary, decisions, action items, jobs, report files, activity entries for the meeting, assistant conversations scoped to the meeting, and the text of assistant answers in the workspace that cited it |
| Delete audio only | The audio file. Transcript and analysis are kept, and the recording is marked deleted |
| Delete report | The report file and its record |
| Delete workspace (owner) | Everything in the workspace, including files |
| Delete account | The user, and every workspace where they are the only owner, including files. Memberships elsewhere are removed |

Files are deleted after the database change is committed. Data already sent to a provider is governed by that provider. PostgreSQL backups made by the host (for example Render's) can keep deleted rows until they expire. There are no embeddings to delete, because none are created.

## Retention

Admins can set **Delete recording audio after N days** per workspace. The worker checks hourly (`RETENTION_SWEEP_MINUTES`) and deletes older audio, skipping meetings that are being processed. Transcripts and analysis are kept until a user deletes them. Without a retention period, data is kept until deleted, except on temporary-storage deployments (`DATABASE_PERSISTENT=false`), where everything is deleted when the server restarts.

## Access control

- Each workspace has members with roles. Viewers can only read. Every API request checks membership and role, and records outside your workspaces return 404.
- Assistant conversations are visible only to their author, and only while they remain a member.
- Passwords are stored as Argon2 hashes. Password-reset tokens are stored as SHA-256 hashes, expire after 30 minutes and work once.

## Speakers and personal characteristics

MeetPilot AI never identifies people by their voice and never infers sensitive characteristics from audio. Speaker names only come from users.

## User responsibilities

Anyone recording a meeting must have the participants' permission and comply with the recording, consent and data-protection laws of every place involved. Do not upload recordings you are not allowed to process. Configure only providers whose terms are acceptable for your data, and set a retention period that matches your obligations.
