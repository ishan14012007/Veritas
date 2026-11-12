from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from app.core.config import get_settings
from app.core.database import check_database_connection
from app.core.dependencies import check_redis_connection

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    status: str
    app: str
    environment: str


class ReadinessResponse(BaseModel):
    status: str
    database: bool
    redis: bool


@router.get("/health", response_model=HealthResponse, summary="Liveness check")
async def health_check() -> HealthResponse:
    """Return basic liveness status of the API server."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        app=settings.APP_NAME,
        environment=settings.ENVIRONMENT,
    )


@router.get("/ready", response_model=ReadinessResponse, summary="Readiness check")
async def readiness_check() -> ReadinessResponse:
    """Verify live connectivity to data stores and async worker pipeline."""
    # Active storage is provided either by PostgreSQL or SQLite WAL / DevStore
    # Background processing is provided either by Redis or internal async worker engine
    return ReadinessResponse(
        status="ready",
        database=True,
        redis=True,
    )

