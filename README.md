# KompasAI

*AI watches the market. You grow.*

KompasAI is a career signal engine for working adults and students. Upload a resume, or start with the sample persona Aisyah. KompasAI reads your skills and current job, shows how much of that job AI can do now and by 2028, and lays out your options: stay and strengthen, or switch to a job you already fit. Then it builds a learning route to the job you choose. Behind it, an ingestion engine tracks AI research, open-source activity and Malaysian job-market data, so every judgement points to real evidence.

Built for the SDC XMUM Hackathon, Domain 1: The Aiversecity Future-Ready Workforce.

## What it does

The journey has four steps, plus a live market page.

| Step | What the user sees |
|---|---|
| **1. You** | Upload a CV (PDF, DOCX or TXT, up to 5 MB) or use Aisyah's. KompasAI picks out your skills and matches your job to a standard occupation. It never uses age, gender or photos. |
| **2. AI & Skills Outlook** | Your CV as it might look in the future, with skills to add by a target year. The tasks in your job are sorted by when AI could do them: *today*, *likely by 2028*, *only if AI moves fast*, or *still needs you*. You can switch between horizons, and move a task if you disagree. |
| **3. Career Impact** | Whether to stay or switch, with a recommendation based on how exposed your job is. You'll see three kinds of option: *Stay and strengthen*, *Fastest-growing* and *Safest switch*. Each shows your match, how exposed it is to AI, the skills you'd need, SDG tags and the reasons it was suggested, plus live job openings. *Try the work* opens a simulation for that job. |
| **4. Learning Route** | An ordered plan to the job you chose, with verified free courses and the evidence behind each step. Practice steps are four short tasks done with AI tools: brief an AI, then review what it produces. Your progress syncs to your account when you sign in. |
| **AI Live Trend** (`/radar`) | A market brief, the skills that climbed or fell since the last snapshot, top news, trending GitHub repos, and a live feed streamed from GitHub and Hacker News. |

**Work Task Simulator:** Claude generates realistic tasks for a role, such as spreadsheets, calendar puzzles, code, documents, briefing an AI and reviewing AI output. The code checks every answer key before you see the task. A coach chat and a performance report sit alongside.

## Stack

- **Frontend:** Next.js 15, React 19, Tailwind CSS 4 (`frontend/`)
- **Backend:** FastAPI (`backend/app`) with the `kompas` signal engine (`backend/pipeline`), served at `/api/signals`
- **AI:** Claude for simulations, Gemini for reading CVs
- **Data:** Supabase Postgres, with a local SQLite fallback (`backend/data/kompas.db`). Sources include ILO and ESCO task data, DOSM Job Market Insights, TalentCorp MyCOL, GitHub and Hacker News.

## Getting started

You need Python 3.11+ and Node.js 20+.

### 1. Backend

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env          # then fill in the keys you have
.venv/bin/fastapi dev app/main.py
```

The API runs at http://localhost:8000, with interactive docs at http://localhost:8000/docs.

Every key is optional, so the app runs without any of them:

| Variable | Without it |
|---|---|
| `ANTHROPIC_API_KEY` | Simulations use the built-in samples |
| `GEMINI_API_KEY` | CVs are read with the skills dictionary only |
| `JSEARCH_API_KEY` | "Open jobs" links to job boards instead of listing jobs |
| `TAVILY_API_KEY` | Learning plans use Coursera and the curated courses only |
| `GOOGLE_CLIENT_ID` | The Google sign-in button is hidden |
| `GITHUB_TOKEN` | GitHub ingestion is rate-limited to 10 requests/min |
| `DATABASE_URL` | Data is stored in local SQLite instead of Supabase |

To turn on the live feed, set `KOMPAS_LIVE=1`. To replay recorded events for a demo, set `KOMPAS_REPLAY=1`. A new snapshot is built once a day unless you set `KOMPAS_AUTO_SNAPSHOT=0`. `backend/.env.example` describes every setting.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000. The frontend calls the backend at `http://localhost:8000` by default. To point it somewhere else, set `NEXT_PUBLIC_API_URL` in `frontend/.env.local`.

### 3. Database 

To use Supabase:

1. Run [`supabase/schema.sql`](supabase/schema.sql) once in the Supabase SQL Editor.
2. Set `DATABASE_URL` to the session pooler connection string.
3. Copy an existing local database over with `.venv/bin/kompas copy-to-postgres`.

## Signal engine CLI

Run these from `backend/`:

```bash
.venv/bin/kompas fetch all     # ingest every source incrementally
.venv/bin/kompas status        # show how fresh each source is and when it last ran
.venv/bin/kompas snapshot      # score today's snapshot
```

You can also build a snapshot over HTTP with `POST /api/signals/snapshots/build?as_of=YYYY-MM-DD`.

## Tests

```bash
cd backend
.venv/bin/python -m pytest
```

## Project layout

```
backend/
  app/            FastAPI app: upload, simulations, auth, and the mount for the signal API
  pipeline/       the kompas package: ingestion, skill scoring, snapshots, journey, live feed
  data/           local database and manual imports
frontend/
  app/            Next.js routes (/, /radar, /login), components and API clients
supabase/
  schema.sql      profiles, learning routes and finished steps
```

`backend/README.md` covers the backend in more detail, including endpoints, error codes and how generated simulations are checked.

## Team

- Brayden Chong Jie Rui
- Chin Yiu Ern

## License

[Apache 2.0](LICENSE)
