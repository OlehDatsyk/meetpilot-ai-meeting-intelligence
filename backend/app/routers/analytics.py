"""Dashboard and analytics. Every number is computed from stored records at request time."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .. import serializers as ser
from ..db import get_db
from ..deps import get_current_user, require_workspace
from ..models import ActionItem, ActivityRecord, Decision, Meeting, ProcessingJob, Project, User

router = APIRouter(tags=["analytics"])


def _week_start(d: datetime | date) -> date:
    d = d.date() if isinstance(d, datetime) else d
    return d - timedelta(days=d.weekday())


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@router.get("/dashboard")
def dashboard(workspace_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ws = require_workspace(db, user, workspace_id)
    total_meetings = db.scalar(select(func.count()).select_from(Meeting).where(Meeting.workspace_id == ws.id)) or 0
    duration = db.scalar(select(func.coalesce(func.sum(Meeting.duration_seconds), 0)).where(Meeting.workspace_id == ws.id))
    processed = db.scalar(select(func.count()).select_from(Meeting).where(Meeting.workspace_id == ws.id,
                                                                         Meeting.status == "completed")) or 0
    in_progress = db.scalar(select(func.count()).select_from(Meeting).where(
        Meeting.workspace_id == ws.id, Meeting.status.in_(("queued", "transcribing", "analysing")))) or 0
    status_counts = dict(db.execute(select(ActionItem.status, func.count()).where(ActionItem.workspace_id == ws.id)
                                    .group_by(ActionItem.status)).all())
    overdue = db.scalar(select(func.count()).select_from(ActionItem).where(
        ActionItem.workspace_id == ws.id, ActionItem.status.in_(("todo", "in_progress")),
        ActionItem.due_date < date.today())) or 0
    decisions = db.scalar(select(func.count()).select_from(Decision).where(Decision.workspace_id == ws.id,
                                                                          Decision.review_status != "rejected")) or 0
    recent = db.scalars(select(Meeting).options(selectinload(Meeting.participants), selectinload(Meeting.project))
                        .where(Meeting.workspace_id == ws.id).order_by(Meeting.meeting_date.desc()).limit(6)).all()
    upcoming = db.execute(select(ActionItem, Meeting).join(Meeting, ActionItem.meeting_id == Meeting.id)
                          .where(ActionItem.workspace_id == ws.id, ActionItem.status.in_(("todo", "in_progress")),
                                 ActionItem.due_date.is_not(None))
                          .order_by(ActionItem.due_date).limit(8)).all()
    activity = db.execute(select(ActivityRecord, User.name).outerjoin(User, ActivityRecord.user_id == User.id)
                          .where(ActivityRecord.workspace_id == ws.id)
                          .order_by(ActivityRecord.created_at.desc()).limit(10)).all()
    # Meetings per week for the last 8 weeks (by meeting date).
    this_week = _week_start(date.today())
    weeks = [this_week - timedelta(weeks=i) for i in range(7, -1, -1)]
    since = datetime.combine(weeks[0], datetime.min.time(), tzinfo=timezone.utc)
    per_week: dict[date, dict[str, float]] = {w: {"meetings": 0, "minutes": 0.0} for w in weeks}
    for md, dur in db.execute(select(Meeting.meeting_date, Meeting.duration_seconds)
                              .where(Meeting.workspace_id == ws.id, Meeting.meeting_date >= since)).all():
        w = _week_start(_aware(md))
        if w in per_week:
            per_week[w]["meetings"] += 1
            per_week[w]["minutes"] += round((dur or 0) / 60, 1)
    return {
        "workspace": {"id": ws.id, "name": ws.name, "is_demo": ws.is_demo},
        "stats": {"total_meetings": total_meetings, "total_duration_seconds": float(duration or 0),
                  "meetings_processed": processed, "meetings_in_progress": in_progress,
                  "actions_outstanding": status_counts.get("todo", 0) + status_counts.get("in_progress", 0),
                  "actions_completed": status_counts.get("completed", 0), "actions_overdue": overdue,
                  "decisions_recorded": decisions},
        "recent_meetings": ser.meetings(db, list(recent)),
        "upcoming_deadlines": [ser.action(a, m) for a, m in upcoming],
        "recent_activity": [{"id": a.id, "action": a.action, "summary": a.summary, "meeting_id": a.meeting_id,
                             "user_name": n, "created_at": a.created_at} for a, n in activity],
        "meetings_per_week": [{"week_start": w.isoformat(), "meetings": v["meetings"], "minutes": v["minutes"]}
                              for w, v in per_week.items()],
    }


@router.get("/analytics")
def analytics(workspace_id: str, weeks: int = Query(12, ge=4, le=52), user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    ws = require_workspace(db, user, workspace_id)
    this_week = _week_start(date.today())
    week_list = [this_week - timedelta(weeks=i) for i in range(weeks - 1, -1, -1)]
    since = datetime.combine(week_list[0], datetime.min.time(), tzinfo=timezone.utc)

    meetings_rows = db.execute(select(Meeting.meeting_date, Meeting.duration_seconds)
                               .where(Meeting.workspace_id == ws.id)).all()
    durations = [d for _, d in meetings_rows if d]
    trend = {w: {"meetings": 0, "minutes": 0.0, "actions_created": 0, "actions_completed": 0} for w in week_list}
    for md, dur in meetings_rows:
        md = _aware(md)
        if md >= since:
            w = _week_start(md)
            if w in trend:
                trend[w]["meetings"] += 1
                trend[w]["minutes"] += round((dur or 0) / 60, 1)
    action_rows = db.execute(select(ActionItem.created_at, ActionItem.completed_at, ActionItem.status)
                             .where(ActionItem.workspace_id == ws.id)).all()
    for created, completed, _ in action_rows:
        created = _aware(created)
        if created >= since and _week_start(created) in trend:
            trend[_week_start(created)]["actions_created"] += 1
        if completed:
            completed = _aware(completed)
            if completed >= since and _week_start(completed) in trend:
                trend[_week_start(completed)]["actions_completed"] += 1
    status_counts: dict[str, int] = defaultdict(int)
    for _, _, st in action_rows:
        status_counts[st] += 1

    by_project = db.execute(select(func.coalesce(Project.name, "No project"), func.count(Decision.id))
                            .select_from(Decision).join(Meeting, Decision.meeting_id == Meeting.id)
                            .outerjoin(Project, Meeting.project_id == Project.id)
                            .where(Decision.workspace_id == ws.id, Decision.review_status != "rejected")
                            .group_by(Project.name)).all()
    jobs = dict(db.execute(select(ProcessingJob.status, func.count()).where(ProcessingJob.workspace_id == ws.id,
                                                                          ProcessingJob.status.in_(("succeeded", "failed")))
                           .group_by(ProcessingJob.status)).all())
    jobs_by_kind = db.execute(select(ProcessingJob.kind, ProcessingJob.status, func.count())
                              .where(ProcessingJob.workspace_id == ws.id,
                                     ProcessingJob.status.in_(("succeeded", "failed")))
                              .group_by(ProcessingJob.kind, ProcessingJob.status)).all()
    finished = jobs.get("succeeded", 0) + jobs.get("failed", 0)
    return {
        "workspace": {"id": ws.id, "name": ws.name, "is_demo": ws.is_demo},
        "totals": {"meetings": len(meetings_rows), "total_duration_seconds": float(sum(durations)),
                   "average_duration_seconds": float(sum(durations) / len(durations)) if durations else None,
                   "meetings_with_duration": len(durations), "actions_created": len(action_rows),
                   "actions_completed": status_counts.get("completed", 0),
                   "actions_outstanding": status_counts.get("todo", 0) + status_counts.get("in_progress", 0),
                   "actions_cancelled": status_counts.get("cancelled", 0)},
        "processing": {"finished_jobs": finished, "succeeded": jobs.get("succeeded", 0), "failed": jobs.get("failed", 0),
                       "success_rate": round(jobs.get("succeeded", 0) / finished, 4) if finished else None,
                       "by_kind": [{"kind": k, "status": s, "count": c} for k, s, c in jobs_by_kind]},
        "decisions_by_project": [{"project": p, "decisions": c} for p, c in by_project],
        "action_status": [{"status": k, "count": v} for k, v in sorted(status_counts.items())],
        "weekly": [{"week_start": w.isoformat(), **v} for w, v in trend.items()],
    }
