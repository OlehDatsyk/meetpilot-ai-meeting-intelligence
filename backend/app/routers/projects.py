"""Projects group meetings inside a workspace."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .. import activity
from .. import schemas as S
from ..db import get_db
from ..deps import get_current_user, get_project_for, require_workspace
from ..models import ActionItem, Decision, Meeting, Project, User

router = APIRouter(prefix="/projects", tags=["projects"])


def project_stats(db: Session, projects: list[Project]) -> list[S.ProjectOut]:
    ids = [p.id for p in projects]
    meet = {}
    acts = {}
    decs = {}
    if ids:
        meet = {pid: (c, last) for pid, c, last in db.execute(
            select(Meeting.project_id, func.count(), func.max(Meeting.meeting_date))
            .where(Meeting.project_id.in_(ids)).group_by(Meeting.project_id)).all()}
        acts = {pid: (t, done, open_) for pid, t, done, open_ in db.execute(
            select(Meeting.project_id, func.count(ActionItem.id),
                   func.sum(case((ActionItem.status == "completed", 1), else_=0)),
                   func.sum(case((ActionItem.status.in_(("todo", "in_progress")), 1), else_=0)))
            .join(Meeting, ActionItem.meeting_id == Meeting.id)
            .where(Meeting.project_id.in_(ids)).group_by(Meeting.project_id)).all()}
        decs = dict(db.execute(select(Meeting.project_id, func.count(Decision.id))
                               .join(Meeting, Decision.meeting_id == Meeting.id)
                               .where(Meeting.project_id.in_(ids), Decision.review_status != "rejected")
                               .group_by(Meeting.project_id)).all())
    out = []
    for p in projects:
        mc, last = meet.get(p.id, (0, None))
        at, ad, ao = acts.get(p.id, (0, 0, 0))
        out.append(S.ProjectOut(id=p.id, workspace_id=p.workspace_id, name=p.name, description=p.description,
                                created_at=p.created_at, updated_at=p.updated_at, meeting_count=mc,
                                action_total=at or 0, action_completed=int(ad or 0), action_open=int(ao or 0),
                                decision_count=decs.get(p.id, 0), last_meeting_at=last))
    return out


@router.get("", response_model=list[S.ProjectOut])
def list_projects(workspace_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace(db, user, workspace_id)
    projects = db.scalars(select(Project).where(Project.workspace_id == workspace_id).order_by(Project.name)).all()
    return project_stats(db, list(projects))


@router.post("", response_model=S.ProjectOut, status_code=201)
def create_project(body: S.ProjectIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace(db, user, body.workspace_id, "member")
    p = Project(workspace_id=body.workspace_id, name=body.name, description=body.description, created_by=user.id)
    db.add(p)
    activity.record(db, body.workspace_id, "project_created", f"Created project “{p.name}”", user_id=user.id)
    db.commit()
    return project_stats(db, [p])[0]


@router.get("/{project_id}", response_model=S.ProjectOut)
def get_project(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return project_stats(db, [get_project_for(db, user, project_id)])[0]


@router.patch("/{project_id}", response_model=S.ProjectOut)
def update_project(project_id: str, body: S.ProjectUpdate, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    p = get_project_for(db, user, project_id, "member")
    if body.name is not None:
        p.name = body.name.strip()
    if body.description is not None:
        p.description = body.description.strip()
    db.commit()
    return project_stats(db, [p])[0]


@router.delete("/{project_id}", response_model=S.Message)
def delete_project(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Deletes the project only. Its meetings stay in the workspace without a project."""
    p = get_project_for(db, user, project_id, "admin")
    activity.record(db, p.workspace_id, "project_deleted", f"Deleted project “{p.name}”", user_id=user.id)
    db.delete(p)
    db.commit()
    return S.Message(message="Project deleted. Its meetings were kept without a project.")
