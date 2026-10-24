import os
from pathlib import Path

from dotenv import load_dotenv

# Settings come from the environment; backend/.env fills in anything not already set.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Comma-separated list of origins allowed to call the API (the Next.js dev server by default).
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
    if o.strip()
]

APP_VERSION = "0.1.0"

# PRD FR-1.1: resumes up to 5 MB
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "5")) * 1024 * 1024

# Model for generating and running work simulations: Claude when ANTHROPIC_API_KEY is set, otherwise Gemini.
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-5-5")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
