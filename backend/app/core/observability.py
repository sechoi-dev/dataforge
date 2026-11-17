import json
import logging
import time
import uuid
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Any

from prometheus_client import Counter, Histogram

request_id_context: ContextVar[str] = ContextVar("request_id", default="-")

HTTP_REQUESTS = Counter(
    "dataforge_http_requests_total",
    "HTTP requests processed by the API.",
    ("method", "route", "status"),
)
HTTP_DURATION = Histogram(
    "dataforge_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("method", "route"),
)
JOB_OUTCOMES = Counter(
    "dataforge_job_outcomes_total",
    "Background job terminal outcomes.",
    ("status",),
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "service": getattr(record, "service", "api"),
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", request_id_context.get()),
        }
        for name in (
            "job_id",
            "dataset_id",
            "dataset_version_id",
            "attempt_id",
            "worker_id",
            "method",
            "route",
            "status_code",
            "duration_ms",
        ):
            value = getattr(record, name, None)
            if value is not None:
                payload[name] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"), default=str)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())


def begin_request(candidate: str | None) -> tuple[str, Token[str], float]:
    request_id = candidate.strip()[:128] if candidate and candidate.strip() else str(uuid.uuid4())
    return request_id, request_id_context.set(request_id), time.perf_counter()
