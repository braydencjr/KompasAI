# Kompas API

FastAPI backend for Kompas.

## Setup

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Run

```bash
.venv/bin/fastapi dev app/main.py
```

- API: http://localhost:8000/api/health
- Interactive docs: http://localhost:8000/docs

The server reloads on save. By default it accepts requests from the frontend at `http://localhost:3000`; set `CORS_ORIGINS` (comma-separated) to change that.

## Layout

```
app/
  main.py        app, CORS, router registration
  config.py      settings from environment variables
  routers/       one file per group of endpoints, mounted under /api
```
