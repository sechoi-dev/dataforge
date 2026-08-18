FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system dataforge && adduser --system --ingroup dataforge dataforge

COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

RUN pip install --no-cache-dir .

USER dataforge

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
