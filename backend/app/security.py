"""Password hashing and signed tokens."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from .config import get_settings, resolve_secret_key

_hasher = PasswordHasher()
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# A real hash to verify against when the email is unknown, so login timing does not reveal accounts.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def dummy_verify(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


def _encode(payload: dict[str, Any], lifetime: timedelta) -> str:
    now = datetime.now(timezone.utc)
    body = {**payload, "iat": now, "exp": now + lifetime}
    return jwt.encode(body, resolve_secret_key(get_settings()), algorithm=ALGORITHM)


def _decode(token: str, typ: str) -> dict[str, Any] | None:
    try:
        data = jwt.decode(token, resolve_secret_key(get_settings()), algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    if data.get("typ") != typ:
        return None
    return data


def create_access_token(user_id: str, token_version: int) -> str:
    minutes = get_settings().access_token_minutes
    return _encode({"sub": user_id, "ver": token_version, "typ": "access"}, timedelta(minutes=minutes))


def decode_access_token(token: str) -> dict[str, Any] | None:
    return _decode(token, "access")


def create_media_token(recording_id: str, user_id: str, minutes: int = 15) -> str:
    """Short-lived token so an <audio> element can stream a private recording without a header."""
    return _encode({"rid": recording_id, "sub": user_id, "typ": "media"}, timedelta(minutes=minutes))


def decode_media_token(token: str) -> dict[str, Any] | None:
    return _decode(token, "media")


def new_reset_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
