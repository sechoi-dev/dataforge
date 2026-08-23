from fastapi import FastAPI

from app.api.routes.datasets import router as datasets_router
from app.api.routes.health import router as health_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.versions import router as versions_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.app_name, version="0.3.0")
    application.include_router(health_router)
    application.include_router(datasets_router)
    application.include_router(versions_router)
    application.include_router(jobs_router)
    return application


app = create_app()
