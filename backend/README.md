# Kompas API

FastAPI backend for Kompas.

## Setup

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
```

## Run

From `backend/`:

```bash
.venv/bin/fastapi dev app/main.py
```

- API: http://localhost:8000/api/health
- Interactive docs: http://localhost:8000/docs

The server reloads on save. By default it accepts requests from the frontend at `http://localhost:3000`; set `CORS_ORIGINS` (comma-separated) to change that.

## Test

From `backend/`:

```bash
.venv/bin/python -m pytest
```

## Endpoints

| Method | Path | What it does |
|---|---|---|
| GET | `/api/health` | Liveness check |
| POST | `/api/upload` | Upload a resume PDF (multipart field `file`, max 5 MB); returns the extracted text |

Errors: `415` not a PDF, `413` too large, `422` unreadable, password-protected, or no text found.

## Layout

```
backend/
  app/
    main.py        app, CORS, router registration
    config.py      settings from environment variables
    routers/       one file per group of endpoints, mounted under /api
    services/      logic used by the routers (e.g. PDF text extraction)
  tests/
  requirements.txt
  requirements-dev.txt
```
