# MeetPilot AI API / worker image. Build context: backend/
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

ARG INSTALL_LOCAL_WHISPER=true
COPY requirements.txt requirements-local.txt ./
RUN if [ "$INSTALL_LOCAL_WHISPER" = "true" ]; then pip install -r requirements-local.txt; else pip install -r requirements.txt; fi

COPY . .
RUN if [ "$INSTALL_LOCAL_WHISPER" = "true" ]; then python scripts/download_whisper_model.py tiny /app/models; fi \
 && useradd --create-home --uid 10001 meetpilot && mkdir -p /data && chown -R meetpilot /data /app/models 2>/dev/null || true
USER meetpilot

ENV LOCAL_WHISPER_MODEL_DIR=/app/models STORAGE_ROOT=/data/storage HF_HUB_OFFLINE=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
CMD ["sh", "-c", "python -m alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
