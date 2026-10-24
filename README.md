# KompasAI

AI is reshaping jobs faster than people can keep up. KompasAI turns your resume into a clear, evidence-backed plan for staying ahead, built for working adults and students in Malaysia.

*AI watches the market. You grow.*

## Team Information

| Field | Details |
|---|---|
| Team Name | Chanel |
| Team Domain | Domain 1: The Aiversecity Future-Ready Workforce |
| SDG Track (1–17) | SDG 4: Quality Education, SDG 5: Gender Equality, SDG 8: Decent Work and Economic Growth, SDG 9: Industry, Innovation and Infrastructure, SDG 10: Reduced Inequalities |
| Team Leader | Brayden Chong Jie Rui |
| University | Universiti Malaya |
| Number of Members | 2 |

## Links

| Resource | Link |
|---|---|
| GitHub Repository | https://github.com/braydencjr/KompasAI |
| Live Demo | https://kompas-ai.replit.app |
| Slide Deck | https://drive.google.com/file/d/1XDuRluHDDoYh7Xji9sER7cgqHZuVnAAh/view?usp=sharing |
| Demo Video | https://youtu.be/TH13qwtQn90 |

## Overview

### Problem

AI is changing jobs faster than workers can tell which of their skills still matter. Working adults and students in Malaysia have no clear, trustworthy way to see which parts of their own job AI can already do, which skills are gaining value, or what to learn next. Generic advice and hype don't help someone decide whether to stay in their role or switch. Without evidence, people either ignore the change or retrain for the wrong job.

### Solution

KompasAI turns a resume into a personal, evidence-backed career outlook. Gemini reads the resume and every skill it reports must quote the resume word for word, so nothing is made up. Each task in the user's job is scored with the ILO's 2025 Generative AI exposure index, and each skill is checked against Malaysian job demand (DOSM, TalentCorp MyCOL), the ESCO skills catalogue, and live AI activity on arXiv, GitHub and Hacker News. The result is a clear choice between staying and strengthening or switching, with a learning route of free courses and hands-on AI practice, and every judgement links to its source.

### Key Features

- **Resume reading:** Upload a resume (PDF, DOCX or TXT, up to 5 MB) or use the sample persona Aisyah. KompasAI picks out your skills and matches your job to a standard occupation. It never uses age, gender or photos.
- **AI & Skills Outlook:** Your resume as employers may read it in the future, with skills that gain value, skills AI can take over, and skills to add. Each task in your job is sorted by when AI could do it, and you can move a task if you disagree.
- **Career Impact:** Whether to stay or switch, with three kinds of option: *Stay and strengthen*, *Fastest-growing* and *Safest switch*. Each shows your match, AI exposure, skills gap, SDG tags, the reasons it was suggested and live job openings.
- **Learning Route:** An ordered plan to the job you chose, with verified free courses and practice tasks done with AI tools. Progress syncs to your account when you sign in.
- **Work Task Simulator:** Claude generates realistic tasks for a role (spreadsheets, code, documents, briefing and reviewing AI output). The code checks every answer key before you see the task, with a coach chat and a performance report.
- **AI Live Trend** (`/radar`): A market brief, the skills that climbed or fell since the last snapshot, top news, trending GitHub repos and a live feed from GitHub and Hacker News.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15, React 19, Tailwind CSS 4 |
| Backend | Python, FastAPI, with the `kompas` signal engine |
| Database | Supabase Postgres, with a local SQLite fallback |
| AI / Compute | Gemini 2.5 Flash (resume reading, skill matching), Claude (work simulations) |
| Hosting / Dev | Replit |
| Data sources | ILO Generative AI exposure index, ESCO, DOSM Job Market Insights, TalentCorp MyCOL, arXiv, GitHub, Hacker News |

## Project Structure

```
.
├── backend/
│   ├── app/                 # FastAPI app: upload, simulations, auth, and the mount for the signal API
│   ├── pipeline/            # the kompas package: ingestion, skill scoring, snapshots, journey, live feed
│   ├── data/                # local database and manual imports
│   ├── tests/               # backend tests
│   ├── .env.example         # example environment variables
│   └── requirements.txt     # Python dependencies
├── frontend/
│   └── app/                 # Next.js routes (/, /radar, /login), components and API clients
├── supabase/
│   └── schema.sql           # profiles, learning routes and finished steps
├── PRD.md                   # product requirements
├── LICENSE
└── README.md
```

## Architecture

```
User ──► Next.js frontend (Replit) ──► FastAPI backend (Replit, /api/signals)
                                            │
                                            ├──► Gemini: reads the resume, matches skills
                                            ├──► Claude: generates work simulations
                                            ├──► Supabase Postgres: snapshots, profiles, learning routes
                                            └──► Signal engine: ILO, ESCO, DOSM, MyCOL, arXiv, GitHub, Hacker News
                                            │
                                            └──► Response returned to user
```

## How to Run

### Option 1: Run on Replit (Recommended)

1. Open the Replit project, or import this repository via **Create Repl → Import from GitHub**.
2. Open the **Secrets** tab (🔒) and add the variables listed in `backend/.env.example` (see the table below), plus:
   - `NEXT_PUBLIC_API_URL`: the backend's public Replit URL. Next.js reads it at build time, so rebuild after changing it.
   - `CORS_ORIGINS`: the frontend's public Replit URL, so the browser is allowed to call the API.
3. Click **Run**. The Repl starts the backend, then the frontend:

   ```bash
   cd backend && pip install -r requirements.txt && fastapi run app/main.py --port 8000 &
   cd frontend && npm install && npm run build && npm run start
   ```

### Option 2: Run Locally

You need Python 3.11+ and Node.js 20+.

```bash
# 1. Clone the repository
git clone https://github.com/braydencjr/KompasAI.git
cd KompasAI

# 2. Backend: create a virtual environment and install dependencies
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt

# 3. Configure environment variables
cp .env.example .env            # then fill in the keys you have

# 4. Run the backend (http://localhost:8000, docs at /docs)
.venv/bin/fastapi dev app/main.py

# 5. In a second terminal, run the frontend (http://localhost:3000)
cd frontend
npm install
npm run dev
```

The frontend calls the backend at `http://localhost:8000` by default. To point it somewhere else, set `NEXT_PUBLIC_API_URL` in `frontend/.env.local`.

Every key is optional, so the app runs without any of them:

| Variable | Without it |
|---|---|
| `ANTHROPIC_API_KEY` | Simulations use the built-in samples |
| `GEMINI_API_KEY` | Resumes are read with the skills dictionary only |
| `JSEARCH_API_KEY` | "Open jobs" links to job boards instead of listing jobs |
| `TAVILY_API_KEY` | Learning plans use Coursera and the curated courses only |
| `GOOGLE_CLIENT_ID` | The Google sign-in button is hidden |
| `GITHUB_TOKEN` | GitHub ingestion is rate-limited to 10 requests/min |
| `DATABASE_URL` | Data is stored in local SQLite instead of Supabase |

To turn on the live feed, set `KOMPAS_LIVE=1`. A new snapshot is built once a day unless you set `KOMPAS_AUTO_SNAPSHOT=0`.

To use Supabase, run [`supabase/schema.sql`](supabase/schema.sql) once in the Supabase SQL Editor, set `DATABASE_URL` to the session pooler connection string, and copy an existing local database over with `.venv/bin/kompas copy-to-postgres`.

### Signal engine CLI

Run these from `backend/`:

```bash
.venv/bin/kompas fetch all     # ingest every source incrementally
.venv/bin/kompas status        # show how fresh each source is and when it last ran
.venv/bin/kompas snapshot      # score today's snapshot
```

### Run Tests

```bash
cd backend
.venv/bin/python -m pytest
```

## How We Use Replit (Required)

- **Hosting:** The backend and frontend run together in one Repl, deployed with Replit Deployments at the Live Demo link above.
- **Secrets:** API keys (Gemini, Anthropic, Supabase and others) are stored in Replit Secrets, never in the code.
- **Persistence:** Data lives in Supabase, so a redeploy doesn't lose snapshots, profiles or learning routes.

📄 Proof of use: `submission/SDC2026_Chanel_Replit_POU.pdf` (TODO)

## Challenges & Learnings

- **Keeping AI output honest.** An LLM reading a resume can invent skills. We made every skill quote the resume word for word, and drop anything that doesn't, so users can see exactly where each result came from.
- **Reference data, not closed lists.** Real resumes name skills and jobs no fixed list covers. We used ESCO and the ILO index as reference data, and let the LLM match or score anything new against them, then saved the result so the next user gets it instantly.
- **Working when services fail.** Data sources rate-limit and APIs go down. Every key is optional, and the app falls back to keyword matching, cached data or built-in samples instead of breaking.
- **Speed.** The first match for a new resume asks the LLM about every new skill and job. Caching those answers took repeat matches from about 35 seconds to about 2.

## Future Improvements

- [ ] Faster first-time resume matching, with progress shown while the LLM works
- [ ] More Malaysian job-market sources and per-state demand
- [ ] Bahasa Malaysia interface
- [ ] Employer view: which skills a team should build next

## Team

| Name | Role | GitHub |
|---|---|---|
| Brayden Chong Jie Rui | Team Lead / AI | [@braydencjr](https://github.com/braydencjr) |
| Chin Yiu Ern | Fullstack | [@ccyenoc](https://github.com/ccyenoc) |

## Submission Checklist

- [x] Team name, domain (Domain 1 / Domain 2) and SDG track filled in
- [x] Slide deck link added
- [x] Demo video link added
- [ ] Replit used, with proof of use in `submission/`
- [ ] Preliminary submission completed (`SDC2026_Chanel_Preliminary.pdf`)
- [ ] Technology declaration completed (`SDC2026_Chanel_TechDeclaration.pdf`)
- [ ] "How to Run" steps verified
- [ ] No API keys or secrets committed to the repository

## License

This project is licensed under the [Apache License 2.0](LICENSE).
