"""Logging: plain single-line records. Transcript text, audio and secrets are never logged by the app."""

from __future__ import annotations

import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if getattr(root, "_meetpilot_configured", False):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.handlers = [handler]
    root.setLevel(level.upper())
    # Third-party HTTP clients log request URLs and sometimes bodies at DEBUG; keep them quiet.
    for noisy in ("httpx", "httpx2", "httpcore", "openai", "anthropic", "google_genai", "botocore", "urllib3", "faster_whisper"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    root._meetpilot_configured = True  # type: ignore[attr-defined]
