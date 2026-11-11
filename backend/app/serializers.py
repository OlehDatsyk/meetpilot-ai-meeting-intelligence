"""ORM -> response model conversion."""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import schemas as S
from .models import (ActionItem, Decision, Meeting, ProcessingJob, Recording, Report, Speaker, Transcript,
                     TranscriptSegment)
from .services import speaker_name


def participant(p) -> S.ParticipantOut:
    return S.ParticipantOut(id=p.id, name=p.name, email=p.email, role=p.role)


def recording(r: Recording | None) -> S.RecordingOut | None:
    if r is None:
        return None
    return S.RecordingOut(id=r.id, original_filename=r.original_filename, audio_format=r.audio_format,
                          content_type=r.content_type, size_bytes=r.size_bytes, duration_seconds=r.duration_seconds,
                          sample_rate=r.sample_rate, channels=r.channels, created_at=r.created_at,
                          audio_available=r.storage_key is not None, audio_deleted_at=r.audio_deleted_at,
                          audio_deleted_reason=r.audio_deleted_reason)


def job(j: ProcessingJob | None) -> S.JobOut | None:
    if j is None:
        return None
    return S.JobOut(id=j.id, meeting_id=j.meeting_id, kind=j.kind, status=j.status, stage=j.stage,
                    progress_current=j.progress_current, progress_total=j.progress_total, attempts=j.attempts,
                    max_attempts=j.max_attempts, error_code=j.error_code, error_message=j.error_message,
                    provider=j.provider, model=j.model, created_at=j.created_at, started_at=j.started_at,
                    finished_at=j.finished_at, run_after=j.run_after)


def _counts(db: Session, meeting_ids: list[str], model) -> dict[str, int]:
    if not meeting_ids:
        return {}
    rows = db.execute(select(model.meeting_id, func.count()).where(model.meeting_id.in_(meeting_ids))
                      .group_by(model.meeting_id)).all()
    return {m: c for m, c in rows}


def meetings(db: Session, items: list[Meeting]) -> list[S.MeetingOut]:
    ids = [m.id for m in items]
    actions = _counts(db, ids, ActionItem)
    decisions = _counts(db, ids, Decision)
    with_transcript = set(db.scalars(select(Transcript.meeting_id).where(Transcript.meeting_id.in_(ids)))) if ids else set()
    out = []
    for m in items:
        out.append(S.MeetingOut(
            id=m.id, workspace_id=m.workspace_id, project_id=m.project_id,
            project_name=m.project.name if m.project else None, title=m.title, description=m.description,
            meeting_date=m.meeting_date, duration_seconds=m.duration_seconds, status=m.status,
            error_stage=m.error_stage, error_message=m.error_message, is_demo=m.is_demo, created_at=m.created_at,
            updated_at=m.updated_at, participants=[participant(p) for p in m.participants],
            has_transcript=m.id in with_transcript, has_summary=m.summary is not None,
            action_count=actions.get(m.id, 0), decision_count=decisions.get(m.id, 0)))
    return out


def meeting_detail(db: Session, m: Meeting) -> S.MeetingDetailOut:
    base = meetings(db, [m])[0]
    latest = db.scalar(select(ProcessingJob).where(ProcessingJob.meeting_id == m.id)
                       .order_by(ProcessingJob.created_at.desc()).limit(1))
    t = m.transcript
    info = None
    if t:
        info = {"provider": t.provider, "model": t.model, "language": t.language, "has_timestamps": t.has_timestamps,
                "has_diarization": t.has_diarization, "chunk_count": t.chunk_count, "created_at": t.created_at,
                "edited_at": t.edited_at}
    return S.MeetingDetailOut(**base.model_dump(), recording=recording(m.recording), latest_job=job(latest),
                              transcript_info=info)


def speakers(db: Session, meeting_id: str) -> list[S.SpeakerOut]:
    counts = dict(db.execute(select(TranscriptSegment.speaker_id, func.count())
                             .where(TranscriptSegment.meeting_id == meeting_id)
                             .group_by(TranscriptSegment.speaker_id)).all())
    sps = db.scalars(select(Speaker).where(Speaker.meeting_id == meeting_id).order_by(Speaker.ordinal)).all()
    return [S.SpeakerOut(id=s.id, label=s.label, ordinal=s.ordinal, display_name=s.display_name,
                         name=speaker_name(s) or "", segment_count=counts.get(s.id, 0)) for s in sps]


def segment(s: TranscriptSegment) -> S.SegmentOut:
    return S.SegmentOut(id=s.id, position=s.position, start_seconds=s.start_seconds, end_seconds=s.end_seconds,
                        speaker_id=s.speaker_id, speaker_name=speaker_name(s.speaker), text=s.text,
                        original_text=s.original_text, edited=s.text != s.original_text, edited_at=s.edited_at)


def decision(d: Decision, m: Meeting) -> S.DecisionOut:
    return S.DecisionOut(id=d.id, meeting_id=d.meeting_id, meeting_title=m.title, meeting_date=m.meeting_date,
                         project_id=m.project_id, title=d.title, description=d.description,
                         meeting_status=d.meeting_status, review_status=d.review_status, participants=d.participants,
                         source_segment_ids=d.source_segment_ids, excerpt=d.excerpt, origin=d.origin,
                         user_modified=d.user_modified, created_at=d.created_at, updated_at=d.updated_at)


def action(a: ActionItem, m: Meeting) -> S.ActionOut:
    overdue = bool(a.due_date and a.status in ("todo", "in_progress") and a.due_date < date.today())
    return S.ActionOut(id=a.id, meeting_id=a.meeting_id, meeting_title=m.title, meeting_date=m.meeting_date,
                       project_id=m.project_id, title=a.title, description=a.description, owner=a.owner,
                       owner_source=a.owner_source, due_date=a.due_date, due_text=a.due_text,
                       due_source=a.due_source, priority=a.priority, priority_source=a.priority_source,
                       needs_confirmation=a.needs_confirmation, status=a.status, notes=a.notes,
                       source_segment_ids=a.source_segment_ids, excerpt=a.excerpt, origin=a.origin,
                       user_modified=a.user_modified, overdue=overdue, completed_at=a.completed_at,
                       created_at=a.created_at, updated_at=a.updated_at)


def report(r: Report, m: Meeting) -> S.ReportOut:
    return S.ReportOut(id=r.id, meeting_id=r.meeting_id, meeting_title=m.title, format=r.format,
                       size_bytes=r.size_bytes, include_transcript=r.include_transcript, created_at=r.created_at)
