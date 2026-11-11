# Third-party notices

MeetPilot AI's own source code is under the MIT licence ([LICENSE](LICENSE)). It depends on third-party software under its own licences. Dependencies are installed by pip and npm and are not copied into this repository, except for the fonts listed below.

## Bundled in this repository

| Component | Location | Licence |
|---|---|---|
| DejaVu Sans and DejaVu Sans Bold fonts | `backend/app/assets/fonts/` | Bitstream Vera Fonts licence with public-domain DejaVu changes. See `backend/app/assets/fonts/LICENSE_DEJAVU`. Used to render PDF reports in any script |

## Backend dependencies (licences checked from installed package metadata, 2026-11-11)

| Package | Licence |
|---|---|
| FastAPI, SQLAlchemy, Alembic, Pydantic, pydantic-settings, PyJWT, argon2-cffi, faster-whisper, CTranslate2 | MIT |
| Uvicorn, Jinja2, ReportLab, imageio-ffmpeg, NumPy, PyAV, httpx2 | BSD-style |
| openai, anthropic, google-genai, boto3, python-multipart | Apache-2.0 |
| email-validator | Unlicense |
| **psycopg** | **LGPL-3.0-only** |
| **mutagen** | **GPL-2.0-or-later** |

Notes:

- **mutagen (GPL-2.0-or-later)** is imported at runtime to read audio metadata. The MIT licence is compatible with the GPL, but if you distribute MeetPilot AI **together with** mutagen (for example as a Docker image), that combined distribution must meet the GPL's terms.
- **psycopg (LGPL-3.0)** is used unmodified as a dynamically installed library.
- **ffmpeg:** imageio-ffmpeg downloads or bundles an ffmpeg binary, which is under the LGPL or GPL depending on the build. Distributions that include the binary must follow its licence.
- **Whisper models:** the `tiny` model is downloaded at runtime or build time from the Hugging Face Hub (`Systran/faster-whisper-tiny`, converted from OpenAI Whisper, MIT). It is not stored in this repository.

## Frontend dependencies (runtime)

React, React DOM, React Router, TanStack Query and Recharts are MIT. Lucide and the d3 modules used by Recharts are ISC or BSD-3-Clause. Development tools (Vite, TypeScript, Tailwind CSS, Vitest, Testing Library, jsdom) are MIT.

## Demo content

The demo meetings, names and company ("Orbitkit") were written for this project and are fictional. No real recordings are included. The test clip used during development was made with Windows text-to-speech and is not in the repository.
