# Contributing

Thanks for your interest. Issues and pull requests are welcome.

## Development setup

Follow [INSTRUCTION.md](INSTRUCTION.md), or run `Start App.bat` / `Start App.command` once. Then:

```bash
# backend (from the project root)
backend/.venv/bin/pip install -r backend/requirements-dev.txt
backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --reload --port 8000
# frontend
cd frontend && npm ci && npm run dev
```

## Conventions

- **Python:** 3.11+, type hints, SQLAlchemy 2 style (`select()`, `Mapped[...]`), Pydantic 2 models in `schemas.py`. Lines up to 120 characters. Authorise every new endpoint through `deps.py` (`require_workspace`, `get_*_for`), and return 404 for records outside the user's workspaces.
- **Errors:** raise `AppError` (or the helpers in `errors.py`) with a stable `code` and a message that is safe to show users. Never put provider payloads, transcript text or secrets in errors or logs.
- **Providers:** add transcription providers under `app/transcription/` and AI providers under `app/ai/providers.py`, using the vendor's official SDK. Map vendor errors to `TranscriptionError` or `AIProviderError`, with `retryable` set correctly.
- **Database:** change models, then `python -m alembic -c backend/alembic.ini revision --autogenerate -m "..."`, review the migration, and keep `test_migrations_match_models` passing.
- **Frontend:** TypeScript strict mode. All API calls go through `src/lib/api.ts`. Use the components in `src/components/ui.tsx`. No secrets in `VITE_` variables.
- **Honesty in the product:** never show invented data, progress, owners, deadlines or integrations. Label demo content as fictional.

## Branches

`main` is always deployable and deploys to Render automatically. Work on a feature branch (`feature/...`, `fix/...`) and open a pull request into `main`.

## Tests

```bash
cd backend && python -m pytest
cd backend && TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/test python -m pytest   # optional
cd frontend && npm run typecheck && npm test && npm run build
```

Mock providers in tests (see `tests/conftest.py`: `FakeTranscriber`, and `FakeAI` in `tests/test_analysis.py`). Never call real provider APIs from the automated suite.

## Pull requests

- Describe the change and how you tested it.
- Add or update tests and documentation (the README feature table, API_DOCUMENTATION.md, CHANGELOG.md).
- Keep pull requests focused. Do not commit `.env`, databases, recordings or generated reports.
