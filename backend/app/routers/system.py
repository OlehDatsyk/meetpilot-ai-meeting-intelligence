"""Health checks and non-secret configuration status."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .. import __version__
from ..ai import ai_status
from ..audio import ALLOWED_EXTENSIONS, ffmpeg_exe
from ..config import get_settings
from ..db import get_engine
from ..deps import get_current_user
from ..models import User
from ..routers.auth import reset_email_available
from ..storage import StorageError, get_storage
from ..transcription import transcription_status

router = APIRouter(tags=["system"])


@router.get("/health")
def health():
    """Liveness: the process is up. Does not touch the database or any provider."""
    return {"status": "ok", "version": __version__}


@router.get("/health/ready")
def ready():
    """Readiness: database and storage reachable. Never calls transcription or AI providers."""
    checks = {"database": "ok", "storage": "ok"}
    status = 200
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        checks["database"], status = "unavailable", 503
    try:
        get_storage().check()
    except (StorageError, Exception):
        checks["storage"], status = "unavailable", 503
    return JSONResponse({"status": "ready" if status == 200 else "not_ready", **checks}, status_code=status)


@router.get("/api/v1/system/config")
def public_config():
    """Non-secret settings the sign-in pages need before a user is authenticated."""
    s = get_settings()
    return {"version": __version__, "demo_enabled": s.demo_enabled, "password_reset_email": reset_email_available(),
            "environment": s.environment, "database_persistent": s.database_persistent}


@router.get("/api/v1/system/status")
def system_status(_: User = Depends(get_current_user)):
    """Which providers are configured. Never returns keys."""
    s = get_settings()
    return {
        "version": __version__,
        "environment": s.environment,
        "transcription": transcription_status(),
        "ai": ai_status(),
        "storage": {"provider": s.storage_provider, "persistent": s.storage_persistent,
                    "database_persistent": s.database_persistent},
        "uploads": {"max_size_mb": s.max_audio_size_mb, "max_duration_minutes": s.max_audio_duration_minutes,
                    "extensions": ALLOWED_EXTENSIONS, "ffmpeg_available": ffmpeg_exe() is not None},
        "worker": {"embedded": s.embedded_worker},
        "semantic_search": False,
        "password_reset_email": reset_email_available(),
    }
