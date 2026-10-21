from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import APP_VERSION, CORS_ORIGINS
from app.routers import health, upload

app = FastAPI(title="Kompas API", version=APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# All endpoints live under /api so the frontend can proxy a single prefix.
app.include_router(health.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
