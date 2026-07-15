FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN pip install --no-cache-dir uv==0.11.24

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY metricthread ./metricthread

EXPOSE 10000

CMD ["sh", "-c", ".venv/bin/uvicorn metricthread.api:app --host 0.0.0.0 --port ${PORT:-10000}"]
