"""FastAPI application."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.gzip import GZipMiddleware

from . import __version__
from .config import get_settings, resolve_secret_key
from .errors import install_error_handlers
from .logging_setup import configure_logging
from .routers import (analysis, analytics, assistant, auth, demo, meetings, projects, reports, search, system,
                      transcripts, workspaces)

log = logging.getLogger("meetpilot")
API = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    resolve_secret_key(s)  # fail fast in production without a key
    worker = None
    if s.embedded_worker and s.environment != "test":
        from .jobs import Worker
        worker = Worker()
        worker.start_background()
    log.info("MeetPilot AI %s started (%s)", __version__, s.environment)
    yield
    if worker:
        worker.stop()


def create_app() -> FastAPI:
    s = get_settings()
    configure_logging(s.log_level)
    app = FastAPI(title="MeetPilot AI API", version=__version__, lifespan=lifespan,
                  description="Meeting transcription, analysis, decisions and action items.",
                  docs_url=None if s.is_production else "/docs", redoc_url=None,
                  openapi_url=None if s.is_production else "/openapi.json")
    install_error_handlers(app)
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origin_list, allow_credentials=False,
                       allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
                       allow_headers=["Authorization", "Content-Type"], expose_headers=["Content-Disposition"],
                       max_age=600)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        if s.is_production:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if request.url.path.startswith(API):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    app.include_router(system.router)
    for r in (auth, workspaces, projects, meetings, transcripts, analysis, assistant, search, reports, analytics,
              demo):
        app.include_router(r.router, prefix=API)

    _mount_frontend(app, s.serve_frontend_dir)
    return app


def _mount_frontend(app: FastAPI, directory: str) -> None:
    """Optionally serve a built frontend from the API (single-service deployments)."""
    if not directory or not os.path.isdir(directory):
        return
    root = os.path.realpath(directory)
    index = os.path.join(root, "index.html")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path.startswith(("api/", "health")):
            return JSONResponse({"error": {"code": "not_found", "message": "Not found."}}, status_code=404)
        candidate = os.path.realpath(os.path.join(root, path))
        if path and candidate.startswith(root + os.sep) and os.path.isfile(candidate):
            headers = {"Cache-Control": "public, max-age=31536000, immutable"} if "/assets/" in candidate.replace(
                "\\", "/") else {}
            return FileResponse(candidate, headers=headers)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


app = create_app()
