"""Keyword search across meetings, transcripts, speakers, action items, decisions and projects."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, rate_limit, require_workspace
from ..models import ActionItem, Decision, Meeting, Project, User
from ..retrieval import escape_like, query_terms, search_segments
from ..services import speaker_name

router = APIRouter(tags=["search"])


@router.get("/search", dependencies=[Depends(rate_limit("search", 120, 60))])
def search(workspace_id: str, q: str = Query(min_length=2, max_length=200), limit: int = Query(10, ge=1, le=50),
           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace(db, user, workspace_id)
    phrase = q.strip()
    like = f"%{escape_like(phrase)}%"
    terms = query_terms(phrase) or [phrase.lower()]

    meetings = db.scalars(select(Meeting).where(Meeting.workspace_id == workspace_id,
                                                or_(Meeting.title.ilike(like, escape="\\"),
                                                    Meeting.description.ilike(like, escape="\\")))
                          .order_by(Meeting.meeting_date.desc()).limit(limit)).all()
    projects = db.scalars(select(Project).where(Project.workspace_id == workspace_id,
                                                or_(Project.name.ilike(like, escape="\\"),
                                                    Project.description.ilike(like, escape="\\")))
                          .limit(limit)).all()
    actions = db.execute(select(ActionItem, Meeting).join(Meeting, ActionItem.meeting_id == Meeting.id)
                         .where(ActionItem.workspace_id == workspace_id,
                                or_(ActionItem.title.ilike(like, escape="\\"),
                                    ActionItem.description.ilike(like, escape="\\"),
                                    ActionItem.owner.ilike(like, escape="\\"),
                                    ActionItem.notes.ilike(like, escape="\\")))
                         .limit(limit)).all()
    decisions = db.execute(select(Decision, Meeting).join(Meeting, Decision.meeting_id == Meeting.id)
                           .where(Decision.workspace_id == workspace_id,
                                  or_(Decision.title.ilike(like, escape="\\"),
                                      Decision.description.ilike(like, escape="\\")))
                           .limit(limit)).all()
    hits = search_segments(db, [workspace_id], terms, limit=limit * 2)
    return {
        "query": phrase,
        "terms": terms,
        "meetings": [{"id": m.id, "title": m.title, "description": m.description[:200],
                      "meeting_date": m.meeting_date, "status": m.status} for m in meetings],
        "segments": [{"id": h.segment.id, "meeting_id": h.meeting.id, "meeting_title": h.meeting.title,
                      "meeting_date": h.meeting.meeting_date, "position": h.segment.position,
                      "start_seconds": h.segment.start_seconds, "speaker": speaker_name(h.segment.speaker),
                      "text": h.segment.text, "score": round(h.score, 3)} for h in hits],
        "action_items": [{"id": a.id, "meeting_id": m.id, "meeting_title": m.title, "title": a.title,
                          "owner": a.owner, "status": a.status, "due_date": a.due_date} for a, m in actions],
        "decisions": [{"id": d.id, "meeting_id": m.id, "meeting_title": m.title, "title": d.title,
                       "meeting_status": d.meeting_status, "review_status": d.review_status} for d, m in decisions],
        "projects": [{"id": p.id, "name": p.name, "description": p.description[:200]} for p in projects],
    }
