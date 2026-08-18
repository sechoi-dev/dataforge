from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from redis import Redis
from sqlalchemy import Engine, text

from app.core.config import Settings, get_settings
from app.db.session import engine

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]


class DependencyStatus(BaseModel):
    postgres: bool
    redis: bool


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    dependencies: DependencyStatus


def get_engine() -> Engine:
    return engine


def check_postgres(database_engine: Engine) -> bool:
    try:
        with database_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def check_redis(settings: Settings) -> bool:
    client = Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=settings.readiness_timeout_seconds,
        socket_timeout=settings.readiness_timeout_seconds,
    )
    try:
        return bool(client.ping())
    except Exception:
        return False
    finally:
        client.close()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=ReadinessResponse)
def ready(
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    database_engine: Annotated[Engine, Depends(get_engine)],
) -> ReadinessResponse:
    dependencies = DependencyStatus(
        postgres=check_postgres(database_engine),
        redis=check_redis(settings),
    )
    is_ready = dependencies.postgres and dependencies.redis
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ready" if is_ready else "not_ready",
        dependencies=dependencies,
    )
