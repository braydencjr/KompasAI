from fastapi import APIRouter

from app.config import APP_VERSION

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": APP_VERSION}
