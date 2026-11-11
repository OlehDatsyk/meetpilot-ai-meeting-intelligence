"""Workspaces and memberships."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import activity
from .. import schemas as S
from ..db import get_db
from ..deps import get_current_user, require_workspace
from ..errors import AppError, bad_request, conflict, not_found
from ..models import ActivityRecord, User, Workspace, WorkspaceMember
from ..services import delete_workspace, purge_files

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def _out(ws: Workspace, role: str) -> S.WorkspaceOut:
    return S.WorkspaceOut(id=ws.id, name=ws.name, role=role, is_demo=ws.is_demo,
                          recording_retention_days=ws.recording_retention_days, created_at=ws.created_at)


@router.get("", response_model=list[S.WorkspaceOut])
def list_workspaces(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(Workspace, WorkspaceMember.role).join(WorkspaceMember)
                      .where(WorkspaceMember.user_id == user.id).order_by(Workspace.is_demo, Workspace.created_at)).all()
    return [_out(ws, role) for ws, role in rows]


@router.post("", response_model=S.WorkspaceOut, status_code=201)
def create_workspace(body: S.WorkspaceIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    count = db.scalar(select(func.count()).select_from(WorkspaceMember).where(WorkspaceMember.user_id == user.id))
    if (count or 0) >= 20:
        raise bad_request("You can belong to at most 20 workspaces.", "workspace_limit")
    ws = Workspace(name=body.name, created_by=user.id)
    db.add(ws)
    db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner"))
    activity.record(db, ws.id, "workspace_created", "Workspace created", user_id=user.id)
    db.commit()
    return _out(ws, "owner")


@router.patch("/{workspace_id}", response_model=S.WorkspaceOut)
def update_workspace(workspace_id: str, body: S.WorkspaceUpdate, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    ws = require_workspace(db, user, workspace_id, "admin")
    if body.name is not None:
        ws.name = body.name.strip()
    if body.clear_retention:
        ws.recording_retention_days = None
    elif body.recording_retention_days is not None:
        ws.recording_retention_days = body.recording_retention_days
    db.commit()
    m = db.scalar(select(WorkspaceMember.role).where(WorkspaceMember.workspace_id == ws.id,
                                                     WorkspaceMember.user_id == user.id))
    return _out(ws, m or "viewer")


@router.delete("/{workspace_id}", response_model=S.Message)
def remove_workspace(workspace_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ws = require_workspace(db, user, workspace_id, "owner")
    remaining = db.scalar(select(func.count()).select_from(WorkspaceMember).where(WorkspaceMember.user_id == user.id))
    if (remaining or 0) <= 1 and not ws.is_demo:
        raise bad_request("You cannot delete your only workspace. Create another one first.", "last_workspace")
    keys = delete_workspace(db, ws)
    db.commit()
    purge_files(keys)
    return S.Message(message="Workspace and all of its meetings, recordings and reports were deleted.")


@router.get("/{workspace_id}/members", response_model=list[S.MemberOut])
def list_members(workspace_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_workspace(db, user, workspace_id)
    rows = db.execute(select(WorkspaceMember, User).join(User).where(WorkspaceMember.workspace_id == workspace_id)
                      .order_by(WorkspaceMember.created_at)).all()
    return [S.MemberOut(id=m.id, user_id=u.id, name=u.name, email=u.email, role=m.role, created_at=m.created_at)
            for m, u in rows]


@router.post("/{workspace_id}/members", response_model=S.MemberOut, status_code=201)
def add_member(workspace_id: str, body: S.MemberIn, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    ws = require_workspace(db, user, workspace_id, "admin")
    if ws.is_demo:
        raise bad_request("Members cannot be added to a demo workspace.", "demo_workspace")
    target = db.scalar(select(User).where(User.email == body.email.lower()))
    if target is None:
        raise AppError(404, "user_not_found", "No MeetPilot AI account uses this email. Ask them to register first.")
    if db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == ws.id,
                                               WorkspaceMember.user_id == target.id)):
        raise conflict("This person is already a member.", "already_member")
    m = WorkspaceMember(workspace_id=ws.id, user_id=target.id, role=body.role)
    db.add(m)
    activity.record(db, ws.id, "member_added", f"{target.name} joined the workspace as {body.role}", user_id=user.id)
    db.commit()
    return S.MemberOut(id=m.id, user_id=target.id, name=target.name, email=target.email, role=m.role,
                       created_at=m.created_at)


def _owner_count(db: Session, workspace_id: str) -> int:
    return db.scalar(select(func.count()).select_from(WorkspaceMember)
                     .where(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.role == "owner")) or 0


@router.patch("/{workspace_id}/members/{member_id}", response_model=S.MemberOut)
def update_member(workspace_id: str, member_id: str, body: S.MemberUpdate, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    require_workspace(db, user, workspace_id, "owner" if body.role == "owner" else "admin")
    m = db.get(WorkspaceMember, member_id)
    if m is None or m.workspace_id != workspace_id:
        raise not_found("Member")
    if m.role == "owner" and body.role != "owner" and _owner_count(db, workspace_id) <= 1:
        raise bad_request("A workspace needs at least one owner.", "last_owner")
    if m.role == "owner":
        require_workspace(db, user, workspace_id, "owner")
    m.role = body.role
    db.commit()
    u = db.get(User, m.user_id)
    return S.MemberOut(id=m.id, user_id=u.id, name=u.name, email=u.email, role=m.role, created_at=m.created_at)


@router.delete("/{workspace_id}/members/{member_id}", response_model=S.Message)
def remove_member(workspace_id: str, member_id: str, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    m = db.get(WorkspaceMember, member_id)
    if m is None or m.workspace_id != workspace_id:
        require_workspace(db, user, workspace_id)
        raise not_found("Member")
    if m.user_id != user.id:  # anyone may leave; removing others needs admin (owner for owners)
        require_workspace(db, user, workspace_id, "owner" if m.role == "owner" else "admin")
    else:
        require_workspace(db, user, workspace_id)
    if m.role == "owner" and _owner_count(db, workspace_id) <= 1:
        raise bad_request("A workspace needs at least one owner. Transfer ownership or delete the workspace.",
                          "last_owner")
    db.delete(m)
    db.commit()
    return S.Message(message="Member removed.")


@router.get("/{workspace_id}/activity")
def workspace_activity(workspace_id: str, limit: int = 30, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    require_workspace(db, user, workspace_id)
    limit = max(1, min(limit, 100))
    rows = db.execute(select(ActivityRecord, User.name).outerjoin(User, ActivityRecord.user_id == User.id)
                      .where(ActivityRecord.workspace_id == workspace_id)
                      .order_by(ActivityRecord.created_at.desc()).limit(limit)).all()
    return [{"id": a.id, "action": a.action, "summary": a.summary, "meeting_id": a.meeting_id, "user_name": n,
             "created_at": a.created_at} for a, n in rows]

