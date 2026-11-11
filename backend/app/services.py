"""Shared operations: data deletion and speaker naming."""

from __future__ import annotations

import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import (ActivityRecord, AIConversation, AIMessage, Meeting, ProcessingJob, Recording, Speaker, User,
                     Workspace, WorkspaceMember, utcnow)
from .storage import get_storage

log = logging.getLogger("meetpilot.services")


def speaker_name(sp: Speaker | None) -> str | None:
    if sp is None:
        return None
    return sp.display_name or f"Speaker {sp.ordinal}"


def purge_files(keys: list[str]) -> None:
    """Delete stored files. Call after the database commit so a failed commit never loses files."""
    storage = get_storage()
    for key in keys:
        try:
            storage.delete(key)
        except Exception:  # keep deleting the rest; the database rows are removed regardless
            log.warning("Could not delete a stored file (%s)", type(storage).__name__)


def delete_recording_audio(db: Session, rec: Recording, reason: str) -> None:
    """Delete the audio file but keep transcript and analysis."""
    if rec.storage_key:
        purge_files([rec.storage_key])
    rec.storage_key = None
    rec.audio_deleted_at = utcnow()
    rec.audio_deleted_reason = reason


def _scrub_assistant_messages(db: Session, workspace_id: str, meeting_ids: set[str]) -> None:
    """Assistant answers quote meeting content, so answers that cited a deleted meeting are removed."""
    if not meeting_ids:
        return
    convs = db.scalars(select(AIConversation).where(AIConversation.meeting_id.in_(meeting_ids))).all()
    for c in convs:
        db.delete(c)
    q = (select(AIMessage).join(AIConversation, AIMessage.conversation_id == AIConversation.id)
         .where(AIConversation.workspace_id == workspace_id, AIMessage.role == "assistant"))
    for m in db.scalars(q).all():
        if set(m.cited_meeting_ids or []) & meeting_ids:
            m.content = "This answer was removed because a meeting it referred to was deleted."
            m.citations = []
            m.cited_meeting_ids = []


def delete_meeting(db: Session, meeting: Meeting) -> list[str]:
    """Delete a meeting with its recording, transcript, analysis, reports and assistant answers that cite it.
    Returns the storage keys to purge after commit."""
    keys = [r.storage_key for r in meeting.reports]
    if meeting.recording and meeting.recording.storage_key:
        keys.append(meeting.recording.storage_key)
    for job in meeting.jobs:
        job.cancel_requested = True
    _scrub_assistant_messages(db, meeting.workspace_id, {meeting.id})
    db.execute(delete(ActivityRecord).where(ActivityRecord.meeting_id == meeting.id))
    db.delete(meeting)
    db.flush()
    return keys


def delete_workspace(db: Session, ws: Workspace) -> list[str]:
    meetings = db.scalars(select(Meeting).where(Meeting.workspace_id == ws.id)).all()
    keys: list[str] = []
    for m in meetings:
        keys += [r.storage_key for r in m.reports]
        if m.recording and m.recording.storage_key:
            keys.append(m.recording.storage_key)
    db.execute(delete(ProcessingJob).where(ProcessingJob.workspace_id == ws.id))
    _scrub_assistant_messages(db, ws.id, {m.id for m in meetings})
    db.delete(ws)
    db.flush()
    return keys


def delete_user_account(db: Session, user: User) -> list[str]:
    """Delete the user and every workspace in which they are the only owner. Returns keys to purge."""
    keys: list[str] = []
    for m in db.scalars(select(WorkspaceMember).where(WorkspaceMember.user_id == user.id)).all():
        if m.role != "owner":
            continue
        owners = db.scalars(select(WorkspaceMember).where(WorkspaceMember.workspace_id == m.workspace_id,
                                                          WorkspaceMember.role == "owner")).all()
        if len(owners) == 1:
            ws = db.get(Workspace, m.workspace_id)
            if ws:
                keys += delete_workspace(db, ws)
    db.delete(user)
    db.flush()
    return keys

