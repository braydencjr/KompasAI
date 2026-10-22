# Kompas API

FastAPI backend for Kompas.

## Setup

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env
```

Then open `.env` and replace `your-anthropic-api-key` with a real key from https://console.anthropic.com/settings/keys. `.env` is git-ignored; never commit a key. While the placeholder is there, the AI endpoints return `503` and the frontend falls back to its built-in sample simulations, so everything still works without a key.

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
| GET | `/api/simulations/status` | `{"ai": true}` when an API key is configured |
| POST | `/api/simulations` | Generates a 4-task work simulation for a role with Claude (cached per role; `"fresh": true` writes a new one) |
| POST | `/api/simulations/brief` | Runs the "Direct the AI" task: Claude plays the AI tool, replies to the user's brief and grades it against the rubric |

Upload errors: `415` not a PDF, `413` too large, `422` unreadable, password-protected, or no text found.

Simulation errors: `503` AI not configured (no key, or the key was rejected), `502` the AI call failed or couldn't produce a valid simulation.

### How generated simulations are kept correct

Claude writes the scenario; code checks it before anyone sees it:

- **Spreadsheets:** Claude gives the *formula* for each answer cell, and the frontend computes the expected values with its own formula engine, so a wrong mental sum by the model can't produce a wrong answer key.
- **Calendars:** the backend searches every arrangement and rejects a puzzle with no valid solution.
- **Code:** Claude ships a reference solution; the frontend runs it against the tests and rejects the task if it fails.
- **Structure:** exactly four tasks (core, core, AI brief, AI review), each with its content; one retry with the problems listed, then `502`.

Model and settings live in `.env` (`ANTHROPIC_MODEL`, default `claude-opus-5-5`). Requests opt into server-side refusal fallbacks (`fallbacks: "default"`).

## Layout

```
backend/
  app/
    main.py        app, CORS, router registration
    config.py      settings from environment variables
    routers/       one file per group of endpoints, mounted under /api
    services/      logic used by the routers (PDF text extraction, Claude calls, simulations)
  tests/
  requirements.txt
  requirements-dev.txt
```
