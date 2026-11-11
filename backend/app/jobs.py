"""Database-backed job queue and the transcription / analysis pipelines.

Jobs live in the `processing_jobs` table, so no extra queue service is needed. A worker claims a job with a
conditional UPDATE (safe with several workers), records real progress (for example "part 2 of 3"), retries
retryable failures with back-off, honours cancellation between steps and recovers jobs whose worker died.
The worker runs either inside the API process (EMBEDDED_WORKER=true) or as `python -m app.worker`.
"""

from __future__ import annotations

import contextlib
import logging
import os
import socket
import tempfile
import threading
import time
from datetime import timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from . import activity
from .ai import AINotConfigured, AIProviderError, get_ai_client
from .ai.analysis import SegmentView, ground, run_analysis
from .audio import FFmpegError, plan_chunks, transcode_to_mp3
from .config import get_settings
from .db import SessionLocal
from .errors import conflict
from .models import (ActionItem, Decision, Meeting, MeetingSummary, ProcessingJob, Recording, Speaker, Transcript,
                     TranscriptSegment, Workspace, utcnow)
from .services import delete_recording_audio, speaker_name
from .storage import StorageError, get_storage
from .transcription import TranscriptionError, get_transcription_provider
from .transcription.base import RawSegment, TranscriptionProvider

log = logging.getLogger("meetpilot.jobs")
ACTIVE = ("queued", "running")
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"


class JobCancelled(Exception):
    pass


class JobFailure(Exception):
    def __init__(self, message: str, code: str, retryable: bool = False):
        super().__init__(message)
        self.message = message
        self.code = code
        self.retryable = retryable


# --- Enqueueing --------------------------------------------------------------------------------

def active_job(db: Session, meeting_id: str) -> ProcessingJob | None:
    return db.scalar(select(ProcessingJob).where(ProcessingJob.meeting_id == meeting_id,
                                                 ProcessingJob.status.in_(ACTIVE)))


def enqueue(db: Session, meeting: Meeting, kind: str, user_id: str | None) -> ProcessingJob:
    """Create a job. Only one active job per meeting is allowed (duplicate prevention)."""
    existing = active_job(db, meeting.id)
    if existing is not None:
        raise conflict("This meeting is already being processed.", "job_in_progress",
                       {"job_id": existing.id, "kind": existing.kind})
    job = ProcessingJob(meeting_id=meeting.id, workspace_id=meeting.workspace_id, kind=kind, status="queued",
                        max_attempts=get_settings().job_max_attempts, created_by=user_id,
                        stage="Waiting for a worker")
    db.add(job)
    meeting.status = "queued"
    meeting.error_stage = None
    meeting.error_message = None
    db.flush()
    return job


# --- Claiming ----------------------------------------------------------------------------------

def recover_stale_jobs(db: Session) -> int:
    """Requeue (or fail) running jobs whose worker stopped updating them."""
    cutoff = utcnow() - timedelta(seconds=get_settings().job_timeout_seconds)
    stale = db.scalars(select(ProcessingJob).where(ProcessingJob.status == "running",
                                                   ProcessingJob.locked_at < cutoff)).all()
    for job in stale:
        meeting = db.get(Meeting, job.meeting_id)
        if job.attempts < job.max_attempts and not job.cancel_requested:
            job.status, job.locked_at, job.locked_by = "queued", None, None
            job.stage = "Restarting after the previous attempt timed out"
            job.run_after = utcnow()
            if meeting:
                meeting.status = "queued"
        else:
            _finish_failed(db, job, meeting, "The job timed out.", "timeout")
    db.commit()
    return len(stale)


def claim_next(db: Session) -> ProcessingJob | None:
    now = utcnow()
    candidates = db.scalars(select(ProcessingJob.id).where(ProcessingJob.status == "queued",
                                                           ProcessingJob.run_after <= now)
                            .order_by(ProcessingJob.created_at).limit(5)).all()
    for job_id in candidates:
        res = db.execute(update(ProcessingJob)
                         .where(ProcessingJob.id == job_id, ProcessingJob.status == "queued")
                         .values(status="running", locked_at=now, locked_by=WORKER_ID,
                                 attempts=ProcessingJob.attempts + 1, started_at=now)
                         .execution_options(synchronize_session=False))
        db.commit()
        if res.rowcount == 1:
            return db.get(ProcessingJob, job_id)
    return None


# --- Running -----------------------------------------------------------------------------------

def _heartbeat(db: Session, job: ProcessingJob, stage: str, current: int | None = None,
               total: int | None = None) -> None:
    cancelled = db.scalar(select(ProcessingJob.cancel_requested).where(ProcessingJob.id == job.id))
    if cancelled is None or cancelled:  # None: the meeting (and its job) was deleted
        raise JobCancelled()
    job.stage = stage
    job.progress_current = current
    job.progress_total = total
    job.locked_at = utcnow()
    db.commit()


def _finish_failed(db: Session, job: ProcessingJob, meeting: Meeting | None, message: str, code: str) -> None:
    job.status = "failed"
    job.error_message = message
    job.error_code = code
    job.finished_at = utcnow()
    job.locked_at = None
    if meeting:
        meeting.status = "failed"
        meeting.error_stage = job.kind
        meeting.error_message = message
        activity.record(db, meeting.workspace_id, f"{job.kind}_failed",
                        f"{'Transcription' if job.kind == 'transcription' else 'Analysis'} failed for "
                        f"“{meeting.title}”", meeting_id=meeting.id)


def run_job(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(ProcessingJob, job_id)
        if job is None:
            return
        meeting = db.get(Meeting, job.meeting_id)
        if meeting is None:
            db.delete(job)
            db.commit()
            return
        try:
            if job.cancel_requested:
                raise JobCancelled()
            if job.kind == "transcription":
                _run_transcription(db, job, meeting)
            elif job.kind == "analysis":
                _run_analysis(db, job, meeting)
            else:
                raise JobFailure("Unknown job type.", "unknown_job")
            job.status = "succeeded"
            job.finished_at = utcnow()
            job.stage = "Finished"
            job.locked_at = None
            job.error_code = job.error_message = None
            db.commit()
            if job.kind == "transcription":
                _maybe_queue_analysis(db, meeting, job.created_by)
        except JobCancelled:
            db.rollback()
            job = db.get(ProcessingJob, job_id)
            meeting = db.get(Meeting, job.meeting_id) if job else None
            if job:
                job.status, job.finished_at, job.stage, job.locked_at = "cancelled", utcnow(), "Cancelled", None
            if meeting:
                meeting.status = "cancelled"
            db.commit()
        except (JobFailure, TranscriptionError, AIProviderError, StorageError, FFmpegError) as e:
            db.rollback()
            job = db.get(ProcessingJob, job_id)
            if job is None:
                return
            meeting = db.get(Meeting, job.meeting_id)
            message = getattr(e, "message", str(e))
            code = getattr(e, "code", "failed")
            retryable = bool(getattr(e, "retryable", False))
            if retryable and job.attempts < job.max_attempts and not job.cancel_requested:
                delay = min(600, 30 * 2 ** (job.attempts - 1))
                job.status, job.locked_at = "queued", None
                job.run_after = utcnow() + timedelta(seconds=delay)
                job.error_message, job.error_code = message, code
                job.stage = f"Attempt {job.attempts} failed: {message} Retrying in {delay} seconds."
                if meeting:
                    meeting.status = "queued"
            else:
                _finish_failed(db, job, meeting, message, code)
            db.commit()
        except Exception:
            log.exception("Unexpected error in %s job", job.kind if job else "unknown")
            db.rollback()
            job = db.get(ProcessingJob, job_id)
            if job:
                _finish_failed(db, job, db.get(Meeting, job.meeting_id),
                               "An unexpected server error stopped processing.", "internal_error")
                db.commit()
    finally:
        db.close()


def _maybe_queue_analysis(db: Session, meeting: Meeting, user_id: str | None) -> None:
    if not get_settings().auto_analyze:
        return
    try:
        client = get_ai_client()
    except AIProviderError:
        client = None
    if client is None:
        return
    db.refresh(meeting)
    if meeting.status == "transcribed" and active_job(db, meeting.id) is None:
        enqueue(db, meeting, "analysis", user_id)
        db.commit()


# --- Transcription pipeline -------------------------------------------------------------------

def _transcribe_file(provider: TranscriptionProvider, src: str, fmt: str, duration: float | None, size: int,
                     tmpdir: str, on_part, language: str | None, diarize: bool):
    s = get_settings()
    needs_convert = fmt not in provider.accepted_formats or (
        provider.max_upload_bytes is not None and size > provider.max_upload_bytes)
    chunks = plan_chunks(duration or 0, s.transcription_chunk_seconds) if duration else [(0.0, 0.0)]
    if provider.name == "local":  # local models stream the file themselves; no size limit to split for
        chunks = [(0.0, duration or 0.0)]
    results = []
    if len(chunks) == 1 and not needs_convert:
        on_part(1, 1)
        results.append((0.0, provider.transcribe(src, fmt, language, diarize)))
        return results
    for i, (start, length) in enumerate(chunks, 1):
        on_part(i, len(chunks), converting=True)
        part = os.path.join(tmpdir, f"part{i}.mp3")
        transcode_to_mp3(src, part, start if len(chunks) > 1 else None, length if len(chunks) > 1 else None)
        if provider.max_upload_bytes and os.path.getsize(part) > provider.max_upload_bytes:
            raise JobFailure("A part of the recording is still too large for the transcription provider. "
                             "Lower TRANSCRIPTION_CHUNK_SECONDS.", "chunk_too_large")
        on_part(i, len(chunks))
        results.append((start, provider.transcribe(part, "mp3", language, diarize)))
        with contextlib.suppress(OSError):
            os.remove(part)
    return results


def _run_transcription(db: Session, job: ProcessingJob, meeting: Meeting) -> None:
    s = get_settings()
    rec = db.scalar(select(Recording).where(Recording.meeting_id == meeting.id))
    if rec is None or not rec.storage_key:
        raise JobFailure("There is no recording to transcribe.", "no_recording")
    provider = get_transcription_provider()
    if provider is None:
        raise JobFailure("No transcription provider is configured on the server.", "not_configured")
    job.provider, job.model = provider.name, provider.model
    meeting.status = "transcribing"
    _heartbeat(db, job, "Preparing audio")

    def on_part(i: int, n: int, converting: bool = False) -> None:
        verb = "Converting" if converting else "Transcribing"
        stage = f"{verb} part {i} of {n}" if n > 1 else f"{verb} audio"
        _heartbeat(db, job, stage, i - 1, n)  # progress counts finished parts only

    storage = get_storage()
    with tempfile.TemporaryDirectory(prefix="meetpilot-") as tmpdir, storage.local_copy(rec.storage_key) as src:
        results = _transcribe_file(provider, src, rec.audio_format, rec.duration_seconds, rec.size_bytes, tmpdir,
                                   on_part, s.transcription_language or None, s.transcription_diarize)
    _heartbeat(db, job, "Saving transcript", len(results), len(results))

    # Re-transcription replaces the previous transcript and anything derived from it.
    db.execute(delete(TranscriptSegment).where(TranscriptSegment.meeting_id == meeting.id))
    db.execute(delete(Speaker).where(Speaker.meeting_id == meeting.id))
    db.execute(delete(Transcript).where(Transcript.meeting_id == meeting.id))
    db.flush()

    multi = len(results) > 1
    speakers: dict[str, Speaker] = {}
    position = 0
    language = None
    has_ts = all(r.has_timestamps for _, r in results)
    has_dia = any(r.has_diarization for _, r in results)
    for part_index, (offset, result) in enumerate(results, 1):
        language = language or result.language
        for raw in result.segments:
            raw: RawSegment
            sp = None
            if has_dia and raw.speaker:
                # Speaker ids are only consistent within one provider request, so parts are kept apart.
                label = f"P{part_index}-{raw.speaker}" if multi else raw.speaker
                sp = speakers.get(label)
                if sp is None:
                    sp = Speaker(meeting_id=meeting.id, label=label[:60], ordinal=len(speakers) + 1)
                    db.add(sp)
                    db.flush()
                    speakers[label] = sp
            position += 1
            db.add(TranscriptSegment(
                meeting_id=meeting.id, workspace_id=meeting.workspace_id, position=position,
                start_seconds=round(raw.start + offset, 3) if has_ts and raw.start is not None else None,
                end_seconds=round(raw.end + offset, 3) if has_ts and raw.end is not None else None,
                speaker_id=sp.id if sp else None, original_text=raw.text, text=raw.text))
    db.add(Transcript(meeting_id=meeting.id, provider=provider.name, model=provider.model, language=language,
                      has_timestamps=has_ts, has_diarization=has_dia, chunk_count=len(results),
                      details={"speaker_ids_per_part": multi and has_dia}))
    if position == 0:
        raise JobFailure("No speech was detected in the recording.", "no_speech")
    meeting.status = "transcribed"
    activity.record(db, meeting.workspace_id, "transcribed", f"Transcribed “{meeting.title}”",
                    meeting_id=meeting.id)


# --- Analysis pipeline ------------------------------------------------------------------------

def segment_views(db: Session, meeting_id: str) -> list[SegmentView]:
    segs = db.scalars(select(TranscriptSegment).where(TranscriptSegment.meeting_id == meeting_id)
                      .order_by(TranscriptSegment.position)).all()
    return [SegmentView(s.id, s.position, s.text, s.start_seconds, speaker_name(s.speaker)) for s in segs]


def _run_analysis(db: Session, job: ProcessingJob, meeting: Meeting) -> None:
    s = get_settings()
    client = get_ai_client()
    if client is None:
        raise AINotConfigured()
    views = segment_views(db, meeting.id)
    if not views:
        raise JobFailure("There is no transcript to analyse yet.", "no_transcript")
    job.provider, job.model = client.primary.name, client.primary.model
    meeting.status = "analysing"
    _heartbeat(db, job, "Analysing transcript")
    participants = [p.name for p in meeting.participants]
    out, provider, model, chunked = run_analysis(client, meeting.title, meeting.meeting_date, participants, views,
                                                 s.ai_max_input_chars)
    _heartbeat(db, job, "Checking results against the transcript")
    names = participants + [v.speaker_label for v in views if v.speaker_label]
    g = ground(out, views, names)

    db.execute(delete(MeetingSummary).where(MeetingSummary.meeting_id == meeting.id))
    # Keep anything the user created, edited or reviewed; replace untouched AI items.
    db.execute(delete(Decision).where(Decision.meeting_id == meeting.id, Decision.origin == "ai",
                                      Decision.user_modified.is_(False), Decision.review_status == "unreviewed"))
    db.execute(delete(ActionItem).where(ActionItem.meeting_id == meeting.id, ActionItem.origin == "ai",
                                        ActionItem.user_modified.is_(False)))
    db.add(MeetingSummary(meeting_id=meeting.id, executive_summary=g.executive_summary,
                          discussion_points=g.discussion_points, open_questions=g.open_questions, risks=g.risks,
                          follow_ups=g.follow_ups, key_dates=g.key_dates, grounding_notes=g.notes,
                          provider=provider, model=model, chunked=chunked))
    db.flush()
    kept_decisions = {d.title.strip().lower() for d in db.scalars(select(Decision).where(Decision.meeting_id == meeting.id))}
    kept_actions = {a.title.strip().lower() for a in db.scalars(select(ActionItem).where(ActionItem.meeting_id == meeting.id))}
    for d in g.decisions:
        if d.title.strip().lower() in kept_decisions:
            continue  # the user already reviewed or edited this one
        db.add(Decision(meeting_id=meeting.id, workspace_id=meeting.workspace_id, title=d.title,
                        description=d.description, meeting_status=d.status, participants=d.participants,
                        source_segment_ids=d.segment_ids, excerpt=d.excerpt, origin="ai"))
    for a in g.action_items:
        if a.title.strip().lower() in kept_actions:
            continue
        db.add(ActionItem(meeting_id=meeting.id, workspace_id=meeting.workspace_id, title=a.title,
                          description=a.description, owner=a.owner, owner_source="transcript" if a.owner else None,
                          due_date=a.due_date, due_text=a.due_text, due_source=a.due_source, priority=a.priority,
                          priority_source=a.priority_source, needs_confirmation=a.needs_confirmation,
                          source_segment_ids=a.segment_ids, excerpt=a.excerpt, origin="ai"))
    job.provider, job.model = provider, model
    meeting.status = "completed"
    activity.record(db, meeting.workspace_id, "analysed",
                    f"Analysed “{meeting.title}”: {len(g.decisions)} decisions, "
                    f"{len(g.action_items)} action items", meeting_id=meeting.id)


# --- Retention ---------------------------------------------------------------------------------

def sweep_retention(db: Session) -> int:
    """Delete recording audio older than the workspace retention period (transcripts are kept)."""
    count = 0
    for ws in db.scalars(select(Workspace).where(Workspace.recording_retention_days.is_not(None))).all():
        cutoff = utcnow() - timedelta(days=ws.recording_retention_days or 0)
        recs = db.scalars(select(Recording).where(Recording.workspace_id == ws.id,
                                                  Recording.storage_key.is_not(None),
                                                  Recording.created_at < cutoff)).all()
        for rec in recs:
            if active_job(db, rec.meeting_id):
                continue
            delete_recording_audio(db, rec, "retention")
            count += 1
    db.commit()
    return count


# --- Worker loop -------------------------------------------------------------------------------

class Worker:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def run_once(self) -> bool:
        db = SessionLocal()
        try:
            job = claim_next(db)
            job_id = job.id if job else None
        finally:
            db.close()
        if job_id:
            run_job(job_id)
            return True
        return False

    def loop(self) -> None:
        s = get_settings()
        last_maintenance = 0.0
        log.info("Job worker %s started", WORKER_ID)
        while not self._stop.is_set():
            try:
                if time.monotonic() - last_maintenance > s.retention_sweep_minutes * 60:
                    db = SessionLocal()
                    try:
                        recover_stale_jobs(db)
                        sweep_retention(db)
                    finally:
                        db.close()
                    last_maintenance = time.monotonic()
                if not self.run_once():
                    self._stop.wait(s.worker_poll_seconds)
            except Exception:
                log.exception("Worker loop error")
                self._stop.wait(5)
        log.info("Job worker stopped")

    def start_background(self) -> None:
        self._thread = threading.Thread(target=self.loop, name="meetpilot-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 10) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)
