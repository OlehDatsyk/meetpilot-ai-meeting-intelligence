"""Summaries, decisions and action items."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from .. import activity
from .. import schemas as S
from .. import serializers as ser
from ..db import get_db
from ..deps import get_action_for, get_current_user, get_decision_for, get_meeting_for, require_workspace
from ..errors import not_found
from ..models import ActionItem, Decision, Meeting, MeetingSummary, User, utcnow
from ..retrieval import escape_like

router = APIRouter(tags=["analysis"])


@router.get("/meetings/{meeting_id}/summary", response_model=S.SummaryOut)
def get_summary(meeting_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = get_meeting_for(db, user, meeting_id)
    s = db.scalar(select(MeetingSummary).where(MeetingSummary.meeting_id == m.id))
    if s is None:
        raise not_found("Summary")
    return S.SummaryOut(meeting_id=m.id, executive_summary=s.executive_summary,
                        discussion_points=s.discussion_points, open_questions=s.open_questions, risks=s.risks,
                        follow_ups=s.follow_ups, key_dates=s.key_dates, grounding_notes=s.grounding_notes,
                        provider=s.provider, model=s.model, chunked=s.chunked, created_at=s.created_at)


# --- Decisions ---------------------------------------------------------------------------------

@router.get("/decisions", response_model=S.Page[S.DecisionOut])
def list_decisions(workspace_id: str, meeting_id: str | None = None, project_id: str | None = None,
                   meeting_status: str | None = None, review_status: str | None = None, q: str | None = None,
                   page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace(db, user, workspace_id)
    stmt = select(Decision, Meeting).join(Meeting, Decision.meeting_id == Meeting.id) \
        .where(Decision.workspace_id == workspace_id)
    if meeting_id:
        stmt = stmt.where(Decision.meeting_id == meeting_id)
    if project_id:
        stmt = stmt.where(Meeting.project_id == project_id)
    if meeting_status:
        stmt = stmt.where(Decision.meeting_status.in_(meeting_status.split(",")))
    if review_status:
        stmt = stmt.where(Decision.review_status.in_(review_status.split(",")))
    if q:
        like = f"%{escape_like(q.strip())}%"
        stmt = stmt.where(or_(Decision.title.ilike(like, escape="\\"), Decision.description.ilike(like, escape="\\")))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(Meeting.meeting_date.desc(), Decision.created_at)
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return S.Page(items=[ser.decision(d, m) for d, m in rows], total=total, page=page, page_size=page_size)


@router.post("/decisions", response_model=S.DecisionOut, status_code=201)
def create_decision(body: S.DecisionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = get_meeting_for(db, user, body.meeting_id, "member")
    d = Decision(meeting_id=m.id, workspace_id=m.workspace_id, title=body.title.strip(),
                 description=body.description.strip(), meeting_status=body.meeting_status,
                 review_status="confirmed", participants=[p.strip() for p in body.participants if p.strip()],
                 origin="user", user_modified=True)
    db.add(d)
    activity.record(db, m.workspace_id, "decision_added", f"Recorded a decision in “{m.title}”", user.id, m.id)
    db.commit()
    return ser.decision(d, m)


@router.patch("/decisions/{decision_id}", response_model=S.DecisionOut)
def update_decision(decision_id: str, body: S.DecisionUpdate, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    d = get_decision_for(db, user, decision_id, "member")
    for field in ("title", "description", "meeting_status", "review_status"):
        val = getattr(body, field)
        if val is not None:
            setattr(d, field, val.strip() if isinstance(val, str) and field in ("title", "description") else val)
    if body.participants is not None:
        d.participants = [p.strip() for p in body.participants if p.strip()]
    d.user_modified = True
    db.commit()
    return ser.decision(d, db.get(Meeting, d.meeting_id))


@router.delete("/decisions/{decision_id}", response_model=S.Message)
def delete_decision(decision_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d = get_decision_for(db, user, decision_id, "member")
    db.delete(d)
    db.commit()
    return S.Message(message="Decision deleted.")


# --- Action items ------------------------------------------------------------------------------

@router.get("/action-items", response_model=S.Page[S.ActionOut])
def list_actions(workspace_id: str, meeting_id: str | None = None, project_id: str | None = None,
                 status: str | None = None, owner: str | None = None, overdue: bool = False,
                 has_due_date: bool | None = None, q: str | None = None,
                 sort: str = Query("due_asc", pattern="^(due_asc|created_desc|priority)$"),
                 page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace(db, user, workspace_id)
    stmt = select(ActionItem, Meeting).join(Meeting, ActionItem.meeting_id == Meeting.id) \
        .where(ActionItem.workspace_id == workspace_id)
    if meeting_id:
        stmt = stmt.where(ActionItem.meeting_id == meeting_id)
    if project_id:
        stmt = stmt.where(Meeting.project_id == project_id)
    if status:
        stmt = stmt.where(ActionItem.status.in_(status.split(",")))
    if owner == "unassigned":
        stmt = stmt.where(ActionItem.owner.is_(None))
    elif owner:
        stmt = stmt.where(ActionItem.owner.ilike(f"%{escape_like(owner.strip())}%", escape="\\"))
    if overdue:
        stmt = stmt.where(ActionItem.due_date < date.today(), ActionItem.status.in_(("todo", "in_progress")))
    if has_due_date is not None:
        stmt = stmt.where(ActionItem.due_date.is_not(None) if has_due_date else ActionItem.due_date.is_(None))
    if q:
        like = f"%{escape_like(q.strip())}%"
        stmt = stmt.where(or_(ActionItem.title.ilike(like, escape="\\"),
                              ActionItem.description.ilike(like, escape="\\"),
                              ActionItem.notes.ilike(like, escape="\\")))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    if sort == "due_asc":
        order = [ActionItem.due_date.is_(None), ActionItem.due_date.asc(), ActionItem.created_at.desc()]
    elif sort == "priority":
        rank = case((ActionItem.priority == "high", 1), (ActionItem.priority == "medium", 2),
                    (ActionItem.priority == "low", 3), else_=4)
        order = [rank, ActionItem.created_at.desc()]
    else:
        order = [ActionItem.created_at.desc()]
    rows = db.execute(stmt.order_by(*order, ActionItem.id).offset((page - 1) * page_size).limit(page_size)).all()
    return S.Page(items=[ser.action(a, m) for a, m in rows], total=total, page=page, page_size=page_size)


@router.post("/action-items", response_model=S.ActionOut, status_code=201)
def create_action(body: S.ActionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = get_meeting_for(db, user, body.meeting_id, "member")
    owner = (body.owner or "").strip() or None
    a = ActionItem(meeting_id=m.id, workspace_id=m.workspace_id, title=body.title.strip(),
                   description=body.description.strip(), owner=owner, owner_source="user" if owner else None,
                   due_date=body.due_date, due_source="user" if body.due_date else None, priority=body.priority,
                   priority_source="user" if body.priority else None, notes=body.notes, origin="user",
                   user_modified=True)
    db.add(a)
    activity.record(db, m.workspace_id, "action_added", f"Added an action item to “{m.title}”", user.id, m.id)
    db.commit()
    return ser.action(a, m)


@router.patch("/action-items/{action_id}", response_model=S.ActionOut)
def update_action(action_id: str, body: S.ActionUpdate, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    a = get_action_for(db, user, action_id, "member")
    if body.title is not None:
        a.title = body.title.strip()
    if body.description is not None:
        a.description = body.description.strip()
    if body.clear_owner:
        a.owner, a.owner_source = None, None
    elif body.owner is not None and body.owner.strip():
        a.owner, a.owner_source = body.owner.strip(), "user"
    if body.clear_due_date:
        a.due_date, a.due_source, a.due_text = None, None, None
    elif body.due_date is not None:
        a.due_date, a.due_source = body.due_date, "user"
    if body.clear_priority:
        a.priority, a.priority_source = None, None
    elif body.priority is not None:
        a.priority, a.priority_source = body.priority, "user"
    if body.notes is not None:
        a.notes = body.notes
    if body.needs_confirmation is not None:
        a.needs_confirmation = body.needs_confirmation
    if body.status is not None and body.status != a.status:
        a.status = body.status
        a.completed_at = utcnow() if body.status == "completed" else None
        if body.status == "completed":
            m = db.get(Meeting, a.meeting_id)
            activity.record(db, a.workspace_id, "action_completed", f"Completed “{a.title[:120]}”", user.id,
                            m.id if m else None)
    a.user_modified = True
    db.commit()
    return ser.action(a, db.get(Meeting, a.meeting_id))


@router.delete("/action-items/{action_id}", response_model=S.Message)
def delete_action(action_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = get_action_for(db, user, action_id, "member")
    db.delete(a)
    db.commit()
    return S.Message(message="Action item deleted.")
