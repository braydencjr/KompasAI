from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import APP_VERSION, CORS_ORIGINS
from app.routers import auth, health, signals, simulations, upload


@asynccontextmanager
async def lifespan(app: FastAPI):
    # the signal engine's live pollers (only when KOMPAS_LIVE=1 / KOMPAS_REPLAY=1)
    async with signals.background():
        yield


app = FastAPI(title="Kompas API", version=APP_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# All endpoints live under /api so the frontend can proxy a single prefix.
app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
app.include_router(simulations.router, prefix="/api")
app.include_router(signals.router, prefix="/api/signals")
