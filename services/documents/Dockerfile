FROM python:3.13-slim

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "poetry==2.3.4"

COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root

COPY alembic.ini ./
COPY migrations ./migrations
COPY src ./src
COPY templates ./templates

RUN poetry install --only main
