from celery import Celery  # type: ignore[import-untyped]
from celery.signals import setup_logging  # type: ignore[import-untyped]

from app.core.config import get_settings
from app.core.observability import configure_logging

settings = get_settings()

celery_app = Celery(
    "dataforge",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)
celery_app.conf.update(
    broker_connection_retry_on_startup=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "dispatch-scheduled-jobs": {
            "task": "dataforge.dispatch_scheduled_jobs",
            "schedule": 5.0,
        },
        "recover-expired-leases": {
            "task": "dataforge.recover_expired_leases",
            "schedule": 10.0,
        },
    },
)


@setup_logging.connect  # type: ignore[untyped-decorator]
def configure_celery_logging(**_: object) -> None:
    configure_logging(settings.log_level)
