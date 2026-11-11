"""Meetings, recording uploads, processing jobs and private audio streaming."""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import tempfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from .. import activity
from .. import schemas as S
from .. import serializers as ser
from ..ai import get_ai_client
from ..audio import AudioValidationError, inspect_audio
from ..config import get_settings
from ..db import get_db
from ..deps import (get_current_user, get_meeting_for, get_project_for, get_recording_for, membership, rate_limit,
                    require_workspace)
from ..errors import AppError, bad_request, conflict, not_found
from ..jobs import active_job, enqueue
from ..models import Meeting, Participant, ProcessingJob, Recording, User, utcnow
from ..retrieval import escape_like
from ..security import create_media_token, decode_media_token
from ..services import delete_meeting, delete_recording_audio, purge_files
from ..storage import get_storage
from ..transcription import TranscriptionError, get_transcription_provider

router = APIRouter(tags=["meetings"])


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


@router.get("/meetings", response_model=S.Page[S.MeetingOut])
def list_meetings(workspace_id: str, q: str | None = None, project_id: str | None = None,
                  status: str | None = None, date_from: datetime | None = None, date_to: datetime | None = None,
                  sort: str = Query("date_desc", pattern="^(date_desc|date_asc|title_asc|title_desc)$"),
                  page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace(db, user, workspace_id)
    stmt = select(Meeting).where(Meeting.workspace_id == workspace_id)
    if q:
        like = f"%{escape_like(q.strip())}%"
        stmt = stmt.where(or_(Meeting.title.ilike(like, escape="\\"), Meeting.description.ilike(like, escape="\\")))
    if project_id:
        stmt = stmt.where(Meeting.project_id == (None if project_id == "none" else project_id))
    if status:
        stmt = stmt.where(Meeting.status.in_(status.split(",")))
    if date_from:
        stmt = stmt.where(Meeting.meeting_date >= _aware(date_from))
    if date_to:
        stmt = stmt.where(Meeting.meeting_date <= _aware(date_to))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order = {"date_desc": Meeting.meeting_date.desc(), "date_asc": Meeting.meeting_date.asc(),
             "title_asc": func.lower(Meeting.title).asc(), "title_desc": func.lower(Meeting.title).desc()}[sort]
    items = db.scalars(stmt.options(selectinload(Meeting.participants), selectinload(Meeting.project))
                       .order_by(order, Meeting.id).offset((page - 1) * page_size).limit(page_size)).all()
    return S.Page(items=ser.meetings(db, list(items)), total=total, page=page, page_size=page_size)


def _set_participants(meeting: Meeting, people: list[S.ParticipantIn]) -> None:
    meeting.participants = [Participant(name=p.name, email=p.email, role=p.role) for p in people]


@router.post("/meetings", response_model=S.MeetingDetailOut, status_code=201)
def create_meeting(body: S.MeetingIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace(db, user, body.workspace_id, "member")
    if body.project_id:
        p = get_project_for(db, user, body.project_id)
        if p.workspace_id != body.workspace_id:
            raise bad_request("The project belongs to a different workspace.")
    m = Meeting(workspace_id=body.workspace_id, project_id=body.project_id, title=body.title,
                description=body.description, meeting_date=_aware(body.meeting_date) or utcnow(),
                duration_seconds=body.duration_minutes * 60 if body.duration_minutes is not None else None,
                status="draft", created_by=user.id)
    _set_participants(m, body.participants)
    db.add(m)
    db.flush()
    activity.record(db, m.workspace_id, "meeting_created", f"Created meeting “{m.title}”", user.id, m.id)
    db.commit()
    return ser.meeting_detail(db, m)


@router.get("/meetings/{meeting_id}", response_model=S.MeetingDetailOut)
def get_meeting(meeting_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ser.meeting_detail(db, get_meeting_for(db, user, meeting_id))


@router.patch("/meetings/{meeting_id}", response_model=S.MeetingDetailOut)
def update_meeting(meeting_id: str, body: S.MeetingUpdate, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    m = get_meeting_for(db, user, meeting_id, "member")
    if body.title is not None:
        m.title = body.title.strip()
    if body.description is not None:
        m.description = body.description.strip()
    if body.meeting_date is not None:
        m.meeting_date = _aware(body.meeting_date)
    if body.duration_minutes is not None and not (m.recording and m.recording.duration_seconds):
        m.duration_seconds = body.duration_minutes * 60
    if body.clear_project:
        m.project_id = None
    elif body.project_id:
        p = get_project_for(db, user, body.project_id)
        if p.workspace_id != m.workspace_id:
            raise bad_request("The project belongs to a different workspace.")
        m.project_id = p.id
    if body.participants is not None:
        _set_participants(m, body.participants)
    db.commit()
    db.refresh(m)
    return ser.meeting_detail(db, m)


@router.delete("/meetings/{meeting_id}", response_model=S.Message)
def remove_meeting(meeting_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = get_meeting_for(db, user, meeting_id, "member")
    ws_id = m.workspace_id
    keys = delete_meeting(db, m)
    activity.record(db, ws_id, "meeting_deleted", "Deleted a meeting and its recording, transcript and reports",
                    user.id)
    db.commit()
    purge_files(keys)
    return S.Message(message="Meeting deleted with its recording, transcript, analysis and reports.")


# --- Upload ------------------------------------------------------------------------------------

@router.post("/meetings/{meeting_id}/recording", response_model=S.UploadOut, status_code=201,
             dependencies=[Depends(rate_limit("upload", 20, 3600))])
async def upload_recording(meeting_id: str, request: Request, file: UploadFile = File(...),
                           replace: bool = Form(False), auto_transcribe: bool = Form(True),
                           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = get_settings()
    m = get_meeting_for(db, user, meeting_id, "member")
    declared = int(request.headers.get("content-length") or 0)
    if declared > s.max_audio_bytes + 1024 * 1024:
        raise AppError(413, "file_too_large", f"The file is larger than the {s.max_audio_size_mb} MB limit.")
    if active_job(db, m.id):
        raise conflict("This meeting is being processed. Cancel it before replacing the recording.", "job_in_progress")
    if m.recording is not None and not replace:
        raise conflict("This meeting already has a recording. Upload with replace=true to replace it.",
                       "recording_exists")
    filename = os.path.basename(file.filename or "recording")[:255]
    fd, tmp_path = tempfile.mkstemp(prefix="meetpilot-upload-", suffix=os.path.splitext(filename)[1][:10])
    sha = hashlib.sha256()
    size = 0
    try:
        with os.fdopen(fd, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > s.max_audio_bytes:
                    raise AppError(413, "file_too_large", f"The file is larger than the {s.max_audio_size_mb} MB limit.")
                sha.update(chunk)
                out.write(chunk)
        if size == 0:
            raise bad_request("The uploaded file is empty.", "empty_file")
        try:
            info = inspect_audio(tmp_path, filename)
        except AudioValidationError as e:
            raise AppError(415 if e.code in ("unsupported_format", "unrecognised_content", "extension_mismatch")
                           else 422, e.code, e.message) from e
        if info.duration_seconds > s.max_audio_duration_minutes * 60:
            raise AppError(413, "too_long", f"The recording is longer than the {s.max_audio_duration_minutes}-minute "
                                            "limit.")
        digest = sha.hexdigest()
        dupes = db.execute(select(Meeting.id, Meeting.title).join(Recording, Recording.meeting_id == Meeting.id)
                           .where(Recording.workspace_id == m.workspace_id, Recording.sha256 == digest,
                                  Meeting.id != m.id)).all()
        key = f"recordings/{m.workspace_id}/{m.id}/{digest[:16]}.{info.format}"
        get_storage().save_file(key, tmp_path, info.content_type)
    finally:
        with contextlib.suppress(OSError):
            os.remove(tmp_path)
        await file.close()

    old_keys: list[str] = []
    if m.recording is not None:
        if m.recording.storage_key and m.recording.storage_key != key:
            old_keys.append(m.recording.storage_key)
        db.delete(m.recording)
        db.flush()
    rec = Recording(meeting_id=m.id, workspace_id=m.workspace_id, storage_key=key, original_filename=filename,
                    audio_format=info.format, content_type=info.content_type, size_bytes=size,
                    duration_seconds=info.duration_seconds, sample_rate=info.sample_rate, channels=info.channels,
                    sha256=digest, uploaded_by=user.id)
    db.add(rec)
    m.duration_seconds = info.duration_seconds
    m.status = "uploaded"
    m.error_stage = m.error_message = None
    activity.record(db, m.workspace_id, "recording_uploaded", f"Uploaded a recording for “{m.title}”",
                    user.id, m.id)
    job = None
    notice = None
    if auto_transcribe:
        try:
            provider = get_transcription_provider()
        except TranscriptionError as e:
            provider, notice = None, f"Transcription is not available: {e.message}"
        if provider is not None:
            job = enqueue(db, m, "transcription", user.id)
        elif notice is None:
            notice = "No transcription provider is configured on this server, so the recording was stored only."
    db.commit()
    purge_files(old_keys)
    db.refresh(m)
    return S.UploadOut(meeting=ser.meeting_detail(db, m), job=ser.job(job),
                       duplicate_of=[{"meeting_id": i, "title": t} for i, t in dupes], notice=notice)


# --- Processing --------------------------------------------------------------------------------

@router.post("/meetings/{meeting_id}/transcribe", response_model=S.JobOut, status_code=202)
def start_transcription(meeting_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = get_meeting_for(db, user, meeting_id, "member")
    if m.recording is None or not m.recording.storage_key:
        raise bad_request("Upload a recording first. (The audio of this meeting is no longer stored.)"
                          if m.recording else "Upload a recording first.", "no_recording")
    try:
        if get_transcription_provider() is None:
            raise AppError(503, "transcription_not_configured", "No transcription provider is configured on this "
                                                                 "server.")
    except TranscriptionError as e:
        raise AppError(503, "transcription_not_configured", e.message) from e
    job = enqueue(db, m, "transcription", user.id)
    db.commit()
    return ser.job(job)


@router.post("/meetings/{meeting_id}/analyze", response_model=S.JobOut, status_code=202,
             dependencies=[Depends(rate_limit("analyze", 30, 3600))])
def start_analysis(meeting_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = get_meeting_for(db, user, meeting_id, "member")
    if not m.segments:
        raise bad_request("This meeting has no transcript to analyse yet.", "no_transcript")
    if get_ai_client() is None:
        raise AppError(503, "ai_not_configured", "No AI provider is configured on this server.")
    job = enqueue(db, m, "analysis", user.id)
    db.commit()
    return ser.job(job)


@router.get("/meetings/{meeting_id}/jobs", response_model=list[S.JobOut])
def list_jobs(meeting_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = get_meeting_for(db, user, meeting_id)
    jobs = db.scalars(select(ProcessingJob).where(ProcessingJob.meeting_id == m.id)
                      .order_by(ProcessingJob.created_at.desc()).limit(20)).all()
    return [ser.job(j) for j in jobs]


@router.get("/jobs/{job_id}", response_model=S.JobOut)
def get_job(job_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    j = db.get(ProcessingJob, job_id)
    if j is None or membership(db, user, j.workspace_id) is None:
        raise not_found("Job")
    return ser.job(j)


@router.post("/jobs/{job_id}/cancel", response_model=S.JobOut)
def cancel_job(job_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    j = db.get(ProcessingJob, job_id)
    if j is None or membership(db, user, j.workspace_id) is None:
        raise not_found("Job")
    require_workspace(db, user, j.workspace_id, "member")
    if j.status not in ("queued", "running"):
        raise conflict("This job has already finished.", "job_finished")
    j.cancel_requested = True
    if j.status == "queued":
        j.status, j.finished_at, j.stage = "cancelled", utcnow(), "Cancelled"
        m = db.get(Meeting, j.meeting_id)
        if m:
            m.status = "cancelled"
    else:
        j.stage = "Cancelling after the current step"
    db.commit()
    return ser.job(j)


# --- Recording access --------------------------------------------------------------------------

@router.delete("/recordings/{recording_id}/audio", response_model=S.Message)
def delete_audio(recording_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Delete the stored audio but keep the transcript and analysis."""
    rec = get_recording_for(db, user, recording_id, "member")
    if active_job(db, rec.meeting_id):
        raise conflict("Wait for processing to finish before deleting the audio.", "job_in_progress")
    delete_recording_audio(db, rec, "user")
    activity.record(db, rec.workspace_id, "audio_deleted", "Deleted a recording's audio file", user.id,
                    rec.meeting_id)
    db.commit()
    return S.Message(message="The audio file was deleted. The transcript and analysis were kept.")


@router.get("/recordings/{recording_id}/media-url")
def media_url(recording_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rec = get_recording_for(db, user, recording_id)
    if not rec.storage_key:
        raise AppError(410, "audio_deleted", "The audio for this meeting has been deleted.")
    presigned = get_storage().presigned_url(rec.storage_key, rec.content_type, 900)
    if presigned:
        return {"url": presigned, "absolute": True, "expires_in": 900}
    return {"url": f"/api/v1/media/{create_media_token(rec.id, user.id)}", "absolute": False, "expires_in": 900}


_RANGE = re.compile(r"bytes=(\d*)-(\d*)$")


@router.get("/media/{token}", include_in_schema=False)
def stream_media(token: str, request: Request, db: Session = Depends(get_db)):
    data = decode_media_token(token)
    if not data:
        raise AppError(401, "invalid_media_token", "This playback link has expired. Reload the page.")
    rec = db.get(Recording, data.get("rid"))
    user = db.get(User, data.get("sub"))
    if rec is None or user is None or membership(db, user, rec.workspace_id) is None or not rec.storage_key:
        raise not_found("Recording")
    storage = get_storage()
    path = storage.local_path(rec.storage_key)
    if path is None:
        raise AppError(410, "audio_missing", "The audio file is no longer available in storage.")
    size = os.path.getsize(path)
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, no-store"}
    rng = request.headers.get("range")
    if not rng:
        return FileResponse(path, media_type=rec.content_type, headers=headers)
    match = _RANGE.match(rng.strip())
    if not match or (not match.group(1) and not match.group(2)):
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
    if match.group(1):
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else size - 1
    else:
        start = max(0, size - int(match.group(2)))
        end = size - 1
    end = min(end, size - 1)
    if start > end or start >= size:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})

    def body():
        with open(path, "rb") as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = f.read(min(256 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    headers.update({"Content-Range": f"bytes {start}-{end}/{size}", "Content-Length": str(end - start + 1)})
    return StreamingResponse(body(), status_code=206, media_type=rec.content_type, headers=headers)
