"""Transcript viewing and editing, and speaker renaming."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import activity
from .. import schemas as S
from .. import serializers as ser
from ..db import get_db
from ..deps import get_current_user, get_meeting_for
from ..errors import bad_request, not_found
from ..models import Speaker, Transcript, TranscriptSegment, User, utcnow

router = APIRouter(tags=["transcripts"])


@router.get("/meetings/{meeting_id}/transcript", response_model=S.TranscriptOut)
def get_transcript(meeting_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = get_meeting_for(db, user, meeting_id)
    t = db.scalar(select(Transcript).where(Transcript.meeting_id == m.id))
    if t is None:
        raise not_found("Transcript")
    segs = db.scalars(select(TranscriptSegment).options(selectinload(TranscriptSegment.speaker))
                      .where(TranscriptSegment.meeting_id == m.id).order_by(TranscriptSegment.position)).all()
    return S.TranscriptOut(meeting_id=m.id, provider=t.provider, model=t.model, language=t.language,
                           has_timestamps=t.has_timestamps, has_diarization=t.has_diarization,
                           chunk_count=t.chunk_count,
                           speaker_ids_per_part=bool((t.details or {}).get("speaker_ids_per_part")),
                           created_at=t.created_at, edited_at=t.edited_at, speakers=ser.speakers(db, m.id),
                           segments=[ser.segment(s) for s in segs])


def _segment_for(db: Session, user: User, segment_id: str, min_role: str) -> TranscriptSegment:
    seg = db.get(TranscriptSegment, segment_id)
    if seg is None:
        raise not_found("Segment")
    get_meeting_for(db, user, seg.meeting_id, min_role)  # authorisation via the meeting
    return seg


@router.patch("/segments/{segment_id}", response_model=S.SegmentOut)
def edit_segment(segment_id: str, body: S.SegmentUpdate, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """Edit the text or reassign the speaker. The original machine text is always preserved."""
    seg = _segment_for(db, user, segment_id, "member")
    changed = False
    if body.revert:
        seg.text = seg.original_text
        seg.edited_at = None
        seg.edited_by = None
        changed = True
    elif body.text is not None and body.text.strip() != seg.text:
        seg.text = body.text.strip()
        seg.edited_at = utcnow()
        seg.edited_by = user.id
        changed = True
    if "speaker_id" in body.model_fields_set:
        if body.speaker_id is not None:
            sp = db.get(Speaker, body.speaker_id)
            if sp is None or sp.meeting_id != seg.meeting_id:
                raise bad_request("That speaker belongs to a different meeting.")
        seg.speaker_id = body.speaker_id
        seg.edited_at = utcnow()
        seg.edited_by = user.id
        changed = True
    if changed:
        t = db.scalar(select(Transcript).where(Transcript.meeting_id == seg.meeting_id))
        if t:
            t.edited_at = utcnow()
    db.commit()
    db.refresh(seg)
    return ser.segment(seg)


@router.patch("/speakers/{speaker_id}", response_model=S.SpeakerOut)
def rename_speaker(speaker_id: str, body: S.SpeakerUpdate, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """Set a display name. The provider's original speaker id (`label`) is never changed."""
    sp = db.get(Speaker, speaker_id)
    if sp is None:
        raise not_found("Speaker")
    m = get_meeting_for(db, user, sp.meeting_id, "member")
    name = (body.display_name or "").strip() or None
    sp.display_name = name
    activity.record(db, m.workspace_id, "speaker_renamed",
                    f"Renamed Speaker {sp.ordinal} in “{m.title}”" if name else
                    f"Cleared the name of Speaker {sp.ordinal} in “{m.title}”", user.id, m.id)
    db.commit()
    return next(s for s in ser.speakers(db, m.id) if s.id == sp.id)
