"""Registration, sign-in, profile, password changes, password reset and account deletion."""

from __future__ import annotations

import logging
import smtplib
from datetime import timedelta
from email.message import EmailMessage

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .. import activity
from .. import schemas as S
from ..config import get_settings
from ..db import get_db
from ..deps import get_current_user, rate_limit
from ..errors import AppError, conflict
from ..models import PasswordResetToken, User, Workspace, WorkspaceMember, utcnow
from ..security import (create_access_token, dummy_verify, hash_password, hash_token, new_reset_token,
                        verify_password)
from ..services import delete_user_account, purge_files

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger("meetpilot.auth")


def _token(user: User) -> S.TokenOut:
    s = get_settings()
    return S.TokenOut(access_token=create_access_token(user.id, user.token_version),
                      expires_in=s.access_token_minutes * 60, user=S.UserOut.model_validate(user))


@router.post("/register", response_model=S.TokenOut, status_code=201,
             dependencies=[Depends(rate_limit("register", 5, 3600))])
def register(body: S.RegisterIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise conflict("An account with this email already exists.", "email_taken")
    user = User(email=email, name=body.name.strip(), password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    ws = Workspace(name=f"{user.name.split()[0]}'s workspace", created_by=user.id)
    db.add(ws)
    db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner"))
    activity.record(db, ws.id, "workspace_created", "Workspace created", user_id=user.id)
    db.commit()
    return _token(user)


@router.post("/login", response_model=S.TokenOut, dependencies=[Depends(rate_limit("login", 10, 300))])
def login(body: S.LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None:
        dummy_verify(body.password)
        raise AppError(401, "invalid_credentials", "Email or password is incorrect.")
    if not verify_password(body.password, user.password_hash) or not user.is_active:
        raise AppError(401, "invalid_credentials", "Email or password is incorrect.")
    user.last_login_at = utcnow()
    db.commit()
    return _token(user)


@router.post("/logout", response_model=S.Message)
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Revokes every token issued to this user (signs out all devices)."""
    db.execute(update(User).where(User.id == user.id).values(token_version=User.token_version + 1))
    db.commit()
    return S.Message(message="Signed out.")


@router.get("/me", response_model=S.UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.patch("/me", response_model=S.UserOut)
def update_me(body: S.ProfileIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.name = body.name
    db.commit()
    return user


@router.post("/change-password", response_model=S.TokenOut,
             dependencies=[Depends(rate_limit("change_password", 10, 300))])
def change_password(body: S.ChangePasswordIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise AppError(400, "invalid_password", "Current password is incorrect.")
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1  # signs out other sessions
    db.commit()
    return _token(user)


def _send_reset_email(to: str, link: str) -> None:
    s = get_settings()
    msg = EmailMessage()
    msg["Subject"] = "Reset your MeetPilot AI password"
    msg["From"] = s.smtp_from
    msg["To"] = to
    msg.set_content(f"Someone asked to reset the password for this MeetPilot AI account.\n\n"
                    f"Open this link within {s.password_reset_minutes} minutes to choose a new password:\n{link}\n\n"
                    "If this was not you, ignore this email.")
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as smtp:
            if s.smtp_starttls:
                smtp.starttls()
            if s.smtp_username:
                smtp.login(s.smtp_username, s.smtp_password)
            smtp.send_message(msg)
    except Exception as e:
        log.error("Password reset email could not be sent (%s)", type(e).__name__)


def reset_email_available() -> bool:
    s = get_settings()
    return bool(s.smtp_host and s.smtp_from)


@router.post("/password-reset/request", response_model=S.Message,
             dependencies=[Depends(rate_limit("reset_request", 5, 900))])
def request_reset(body: S.ResetRequestIn, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    s = get_settings()
    generic = S.Message(message="If an account exists for this email, a reset link has been sent.")
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None:
        return generic
    token, token_hash = new_reset_token()
    db.add(PasswordResetToken(user_id=user.id, token_hash=token_hash,
                              expires_at=utcnow() + timedelta(minutes=s.password_reset_minutes)))
    db.commit()
    link = f"{s.frontend_url.rstrip('/')}/reset-password?token={token}"
    if reset_email_available():
        tasks.add_task(_send_reset_email, user.email, link)
    elif s.environment == "development":
        # Local development only: there is no mail server, so the link is printed to the server console.
        log.warning("Password reset link (development only, not emailed): %s", link)
    return generic


@router.post("/password-reset/confirm", response_model=S.Message,
             dependencies=[Depends(rate_limit("reset_confirm", 10, 900))])
def confirm_reset(body: S.ResetConfirmIn, db: Session = Depends(get_db)):
    rec = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(body.token)))
    now = utcnow()
    expires = rec.expires_at if rec else None
    if expires is not None and expires.tzinfo is None:  # SQLite returns naive datetimes
        expires = expires.replace(tzinfo=now.tzinfo)
    if rec is None or rec.used_at is not None or expires is None or expires < now:
        raise AppError(400, "invalid_token", "This reset link is invalid or has expired.")
    user = db.get(User, rec.user_id)
    if user is None:
        raise AppError(400, "invalid_token", "This reset link is invalid or has expired.")
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1
    rec.used_at = now
    db.commit()
    return S.Message(message="Your password has been changed. You can sign in now.")


@router.delete("/me", response_model=S.Message, dependencies=[Depends(rate_limit("delete_account", 5, 900))])
def delete_account(body: S.DeleteAccountIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(body.password, user.password_hash):
        raise AppError(400, "invalid_password", "Password is incorrect.")
    keys = delete_user_account(db, user)
    db.commit()
    purge_files(keys)
    return S.Message(message="Your account and the workspaces you solely owned have been deleted.")
