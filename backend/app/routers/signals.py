"""The Kompas signal engine (backend/pipeline) served under /api/signals.

Routes: /health, /snapshots, /concepts, /feed, /feed/stream (SSE), /match, /profile/extract.
Ingestion itself runs from the CLI (`kompas fetch ...`); with KOMPAS_LIVE=1 this server also polls
Hacker News and GitHub for the live feed.
"""

from kompas.api import create_router

router, background = create_router()
