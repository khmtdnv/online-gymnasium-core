FROM python:3.14-slim

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir "poetry==2.3.4"

COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root

COPY src ./src

RUN poetry install --only main