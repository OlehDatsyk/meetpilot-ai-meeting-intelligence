# Changelog

## [1.1.0] - 2026-11-13

### Added
- Public landing page at `/` for signed-out visitors: product introduction, features, how it works, grounding approach, previews of the real app (fictional demo data), use cases, open-source information and a footer with documentation, privacy, contact and source links. Signed-in users still go straight to the dashboard. No testimonials, customer numbers or pricing plans.
- Frontend tests for the landing page.

## [1.0.0] - 2026-11-11

First release.

### Added
- Accounts: registration, sign-in, sign-out (revokes all sessions), password change, password reset by email (SMTP), account deletion.
- Workspaces with owner, admin, member and viewer roles, members, retention settings and deletion.
- Projects with progress based on action items.
- Meetings: create, edit, delete, search, filter and sort. Participants.
- Audio upload (MP3, WAV, M4A, AAC, OGG, FLAC) with content sniffing, metadata extraction, size and duration limits, duplicate detection and upload progress.
- Database-backed job queue with an embedded or separate worker, real progress, retries, timeouts, cancellation and stale-job recovery.
- Transcription providers: OpenAI (with diarisation on `gpt-4o-transcribe-diarize`) and local faster-whisper. Conversion and splitting with ffmpeg.
- Transcript viewer with playback, seeking, search, speaker filter, editing that keeps the original text, and speaker naming.
- AI analysis with OpenAI, Anthropic and Gemini adapters and fallbacks: summary, discussion points, decisions, action items, questions, risks, follow-ups and key dates, with grounding checks.
- Action item and decision management, review workflow, and CSV, Markdown and ICS exports.
- Grounded AI assistant with citations, and a retrieval-only mode without an AI key.
- Keyword search across all records.
- PDF and HTML reports, plus transcript, summary, action item and decision exports.
- Dashboard and analytics computed from stored records.
- Public demo page and optional demo workspace with fictional data.
- Local and S3 storage, private playback links, deletion of meetings, audio, workspaces and accounts.
- Start scripts for Windows and macOS, Docker Compose, Render Blueprint, automated tests and documentation.
