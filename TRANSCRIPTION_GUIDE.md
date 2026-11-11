# Transcription guide

Transcription is separate from AI analysis: a server can transcribe without an AI provider, and analyse transcripts without a transcription provider (for example, demo data).

## Supported audio formats

| Format | Extensions | Detected by | OpenAI | Local Whisper |
|---|---|---|---|---|
| MP3 | `.mp3` | ID3 tag or MPEG frame sync | sent as is | yes |
| WAV | `.wav`, `.wave` | `RIFF....WAVE` | sent as is | yes |
| M4A (AAC/ALAC in MP4) | `.m4a` | `ftyp` box, audio codec checked | sent as is | yes |
| AAC (ADTS) | `.aac` | ADTS sync word | **converted to MP3** (OpenAI does not accept raw AAC) | yes |
| OGG (Vorbis/Opus) | `.ogg`, `.oga`, `.opus` | `OggS` | sent as is | yes |
| FLAC | `.flac` | `fLaC` | sent as is | yes |

Each upload is checked in this order:

1. the extension must be one of the above,
2. the first bytes must match a known container,
3. the extension must match that container,
4. the file must parse with mutagen and have a positive duration.

A text or HTML file renamed to `.mp3` is rejected (`415`). A truncated WAV is rejected (`422`). Size (`MAX_AUDIO_SIZE_MB`) and duration (`MAX_AUDIO_DURATION_MINUTES`) are enforced, and the upload stops as soon as the size limit is passed. Rejected files are never stored. A SHA-256 hash flags the same file uploaded to another meeting in the workspace.

## Providers

### OpenAI (`TRANSCRIPTION_PROVIDER=openai`)

| `TRANSCRIPTION_MODEL` | Request | Timestamps | Speakers |
|---|---|---|---|
| `gpt-4o-transcribe-diarize` (default) | `response_format=diarized_json`, `chunking_strategy=auto` | per segment | yes ("A", "B", ... shown as Speaker 1, 2) |
| `whisper-1` | `verbose_json` with segment timestamps | per segment | no |
| `gpt-transcribe`, `gpt-4o-transcribe`, `gpt-4o-mini-transcribe` | `json` | none | no |

For text-only models the text is split into sentence groups without timestamps; MeetPilot AI never invents times. OpenAI accepts up to 25 MB per request, so larger files are converted to 16 kHz mono MP3 at 48 kbit/s (about 21 MB per hour). Recordings longer than `TRANSCRIPTION_CHUNK_SECONDS` (default 20 minutes) are split into parts.

The installed OpenAI SDK lists a shutdown date of 2027-02-26 for `whisper-1` and the `gpt-4o-*` transcription models. After that, set `TRANSCRIPTION_MODEL` to a supported model. Check OpenAI's deprecations page.

Errors map to safe messages: invalid key (not retried), rate limit or quota (retried with back-off), rejected audio (not retried), timeouts, connection errors and 5xx (retried).

### Local Whisper (`TRANSCRIPTION_PROVIDER=local`)

[faster-whisper](https://github.com/SYSTRAN/faster-whisper) runs on the server CPU (int8). Audio never leaves the server. Audio is decoded with ffmpeg in 10-minute windows, so memory use stays flat for long recordings. The language is detected from the first window. Voice activity detection skips silence.

- No speaker detection.
- Models: `tiny` (default, about 75 MB), `base`, `small`, `medium`. Larger models are more accurate but slower and need more RAM.
- Measured on the development machine (Windows, 16 threads, `tiny`): a 30-second clip transcribed correctly, and the API process peaked at about 230 MB, including the embedded worker. Render's shared CPUs will be slower.
- The model downloads from the Hugging Face Hub on first use, or at build time with `python scripts/download_whisper_model.py`. Set `HF_HUB_OFFLINE=1` when the model is already present.

## Processing workflow

1. Upload → `uploaded` → job `queued` (only when a provider is configured).
2. A worker claims the job → `transcribing`, with stages such as "Converting part 1 of 3" and "Transcribing part 2 of 3".
3. Each part's timestamps are shifted by its start offset and segments are stored in order with `original_text`.
4. → `transcribed`. If an AI provider is configured, analysis is queued automatically.
5. Failures → `failed` with `error_stage = transcription` and a safe message. Retryable errors are retried up to `JOB_MAX_ATTEMPTS` times.

Cancel from the meeting page: queued jobs stop at once, running jobs stop after the current part. Re-transcribing replaces the earlier transcript and speakers.

## Timestamps

Stored per segment in seconds (`start_seconds`, `end_seconds`) only when the provider returned them. The viewer then shows them, plays from them and highlights the current line, and SRT and VTT exports become available. Without timestamps, segments show their number and subtitle export is refused.

## Speaker diarisation

- Speakers appear as **Speaker 1, Speaker 2...** in order of appearance. The provider's original ID is kept in `speakers.label` and never changes.
- Users can name speakers and move a line to another speaker. Names only come from users; voices are never used to identify anyone, and no personal characteristics are inferred.
- A provider's speaker IDs are only consistent within one request. When a recording is split into parts, IDs are kept per part (`P2-A`), the viewer shows a notice, and users can give matching speakers the same name.

## Limitations

- Accuracy depends on the provider, model, audio quality, accents and overlapping speech. Transcripts can be edited.
- Local Whisper `tiny` is fast but makes more mistakes than larger or cloud models.
- No live (streaming) transcription.
- The OpenAI path is tested with mocked HTTP responses only; it has not been run against the live API in this project.
