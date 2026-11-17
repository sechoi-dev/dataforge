import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.routes.comparisons import router as comparisons_router
from app.api.routes.datasets import router as datasets_router
from app.api.routes.health import router as health_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.rules import router as rules_router
from app.api.routes.versions import router as versions_router
from app.core.config import get_settings
from app.core.observability import (
    HTTP_DURATION,
    HTTP_REQUESTS,
    begin_request,
    configure_logging,
    request_id_context,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("DataForge API started", extra={"service": "api"})
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)

    @application.middleware("http")
    async def observe_request(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id, token, started = begin_request(request.headers.get("X-Request-ID"))
        try:
            response = await call_next(request)
            route_object = request.scope.get("route")
            route = getattr(route_object, "path", "unmatched")
            duration = time.perf_counter() - started
            HTTP_REQUESTS.labels(request.method, route, str(response.status_code)).inc()
            HTTP_DURATION.labels(request.method, route).observe(duration)
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "HTTP request completed",
                extra={
                    "method": request.method,
                    "route": route,
                    "status_code": response.status_code,
                    "duration_ms": round(duration * 1_000, 2),
                },
            )
            return response
        finally:
            request_id_context.reset(token)

    @application.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    application.include_router(health_router)
    application.include_router(datasets_router)
    application.include_router(versions_router)
    application.include_router(jobs_router)
    application.include_router(rules_router)
    application.include_router(comparisons_router)
    return application


app = create_app()
