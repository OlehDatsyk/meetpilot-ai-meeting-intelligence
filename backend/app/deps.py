"""Request dependencies: authentication, workspace authorisation and rate limiting.

Authorisation is enforced here on the server for every request, independently of the frontend.
Records the user cannot see are reported as 404 so their existence is not revealed.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .errors import AppError, forbidden, not_found
from .models import (ActionItem, Decision, Meeting, Project, Recording, Report, User, Workspace,
                     WorkspaceMember)
from .security import decode_access_token

_bearer = HTTPBearer(auto_error=False)

ROLE_RANK = {"viewer": 0, "member": 1, "admin": 2, "owner": 3}


def _unauthorized(message: str = "Please sign in.") -> AppError:
    return AppError(401, "unauthorized", message, headers={"WWW-Authenticate": "Bearer"})


def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
                     db: Session = Depends(get_db)) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise _unauthorized()
    data = decode_access_token(creds.credentials)
    if not data:
        raise _unauthorized("Your session has expired. Please sign in again.")
    user = db.get(User, data.get("sub"))
    if user is None or not user.is_active or user.token_version != data.get("ver"):
        raise _unauthorized("Your session has expired. Please sign in again.")
    return user


def membership(db: Session, user: User, workspace_id: str) -> WorkspaceMember | None:
    return db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id,
                                                   WorkspaceMember.user_id == user.id))


def require_workspace(db: Session, user: User, workspace_id: str | None, min_role: str = "viewer") -> Workspace:
    if not workspace_id:
        raise AppError(400, "workspace_required", "workspace_id is required.")
    m = membership(db, user, workspace_id)
    if m is None:
        raise not_found("Workspace")
    if ROLE_RANK[m.role] < ROLE_RANK[min_role]:
        raise forbidden("Your role in this workspace does not allow this action.")
    ws = db.get(Workspace, workspace_id)
    if ws is None:
        raise not_found("Workspace")
    return ws


def user_workspace_ids(db: Session, user: User) -> list[str]:
    return list(db.scalars(select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user.id)))


def _load(db: Session, user: User, model, obj_id: str, what: str, min_role: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise not_found(what)
    m = membership(db, user, obj.workspace_id)
    if m is None:
        raise not_found(what)
    if ROLE_RANK[m.role] < ROLE_RANK[min_role]:
        raise forbidden("Your role in this workspace does not allow this action.")
    return obj


def get_meeting_for(db: Session, user: User, meeting_id: str, min_role: str = "viewer") -> Meeting:
    return _load(db, user, Meeting, meeting_id, "Meeting", min_role)


def get_project_for(db: Session, user: User, project_id: str, min_role: str = "viewer") -> Project:
    return _load(db, user, Project, project_id, "Project", min_role)


def get_action_for(db: Session, user: User, action_id: str, min_role: str = "viewer") -> ActionItem:
    return _load(db, user, ActionItem, action_id, "Action item", min_role)


def get_decision_for(db: Session, user: User, decision_id: str, min_role: str = "viewer") -> Decision:
    return _load(db, user, Decision, decision_id, "Decision", min_role)


def get_recording_for(db: Session, user: User, recording_id: str, min_role: str = "viewer") -> Recording:
    return _load(db, user, Recording, recording_id, "Recording", min_role)


def get_report_for(db: Session, user: User, report_id: str, min_role: str = "viewer") -> Report:
    return _load(db, user, Report, report_id, "Report", min_role)


# --- Rate limiting -----------------------------------------------------------------------------

class RateLimiter:
    """In-process sliding-window limiter. Limits apply per API process (documented limitation)."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window: float) -> float | None:
        """Record a hit. Returns seconds to wait when over the limit, otherwise None."""
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - window:
                q.popleft()
            if len(q) >= limit:
                return max(1.0, window - (now - q[0]))
            q.append(now)
            if len(self._hits) > 50_000:  # bound memory under abuse
                for k in [k for k, v in self._hits.items() if not v][:10_000]:
                    self._hits.pop(k, None)
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    # Render's proxy appends the address it saw to X-Forwarded-For. Earlier entries are client-controlled,
    # so only the right-most one is used.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(bucket: str, limit: int, window: float = 60.0) -> Callable[[Request], None]:
    def _dep(request: Request) -> None:
        if not get_settings().rate_limit_enabled:
            return
        wait = limiter.hit(f"{bucket}:{client_ip(request)}", limit, window)
        if wait is not None:
            raise AppError(429, "rate_limited", "Too many requests. Please wait and try again.",
                           headers={"Retry-After": str(int(wait))})
    return _dep
