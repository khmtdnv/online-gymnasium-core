# Analytics Layered Structure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Make the analytics service follow the same dependency boundaries as
the Schedule service before finishing its HTTP read API.

**Architecture:** API and Kafka worker are entry points. They use application
read models and `Protocol` ports; infrastructure supplies ClickHouse adapters;
`main.py` composes concrete objects for Uvicorn. This is a file/layout refactor
for existing worker functionality plus one new port for the HTTP read path.

**Tech Stack:** Python 3.14, FastAPI, aiokafka, clickhouse-connect, pytest,
Ruff.

**Spec:** `docs/superpowers/specs/2026-09-19-analytics-read-api-design.md`

## File structure

```text
src/analytics_service/
  application/
    snapshot.py
    workload.py
    ports/workload_repository.py
  infrastructure/
    clickhouse_snapshot_repository.py
    clickhouse_workload_repository.py
  api/app.py
  workers/worker.py
  config.py
  main.py
```

## Task 1: Establish the boundary packages

**Files:**

- Move `snapshot.py` to `application/snapshot.py`.
- Move `workload.py` to `application/workload.py`.
- Move `clickhouse_repository.py` to
  `infrastructure/clickhouse_snapshot_repository.py`.
- Move `workload_repository.py` to
  `infrastructure/clickhouse_workload_repository.py`.
- Move `app.py` to `api/app.py`.
- Move `worker.py` to `workers/worker.py`.
- Create empty `__init__.py` in `application`, `application/ports`,
  `infrastructure`, `api`, and `workers`.

- [ ] Change existing test imports first:

```python
from analytics_service.application.workload import ClassDailyWorkload
from analytics_service.infrastructure.clickhouse_workload_repository import (
    ClickHouseWorkloadRepository,
)
from analytics_service.api.app import create_app
from analytics_service.workers import worker
```

- [ ] Run `poetry run pytest -q` and observe `ModuleNotFoundError` for the new
  package structure.

- [ ] Create directories and use `git mv` for every listed move. Update each
  source import: adapters import models from `application`; worker imports
  adapters from `infrastructure`; tests import the target modules.

- [ ] Run:

```bash
poetry run pytest -q
poetry run ruff check .
poetry run ruff format --check .
```

## Task 2: Make the API depend on a port, not ClickHouse

**Files:**

- Create `application/ports/workload_repository.py`.
- Modify `api/app.py`.

- [ ] Add this protocol:

```python
from datetime import date
from typing import Protocol

from analytics_service.application.workload import ClassDailyWorkload


class WorkloadRepository(Protocol):
    async def get(
        self,
        *,
        class_id: int,
        day: date,
    ) -> ClassDailyWorkload | None: ...
```

- [ ] In `api/app.py`, remove the import of the concrete ClickHouse adapter.
  Type `repository_factory` as
  `Callable[[], WorkloadRepository]`. Leave the route’s 200/404/503 behaviour
  untouched.

- [ ] Run the same full analytics test and Ruff commands. The fake repository
  in `tests/test_api.py` must work without explicit inheritance: it matches the
  port structurally.

## Task 3: Add composition root for Uvicorn

**Files:**

- Create `main.py`.
- Modify `compose.yaml` later in the HTTP-runtime task to point Uvicorn at
  `analytics_service.main:app` and the worker at
  `analytics_service.workers.worker`.

- [ ] Write `main.py` as the one permitted location that imports both outer
  layers:

```python
import clickhouse_connect

from analytics_service.api.app import create_app
from analytics_service.config import AnalyticsApiSettings
from analytics_service.infrastructure.clickhouse_workload_repository import (
    ClickHouseWorkloadRepository,
)

settings = AnalyticsApiSettings()
client = clickhouse_connect.get_client(
    host=settings.clickhouse_host,
    port=settings.clickhouse_port,
    username=settings.clickhouse_user,
    password=settings.clickhouse_password,
)
app = create_app(settings, lambda: ClickHouseWorkloadRepository(client))
```

- [ ] Do not make a ClickHouse request at import time: `get_client()` only
  constructs the client; the query stays inside repository `get()`.

- [ ] Verify with `poetry run pytest -q`, Ruff checks, and
  `docker compose config --quiet` after Compose is changed in the next task.

## Review checklist

- `api` imports the port and application read model, never an infrastructure
  adapter.
- Infrastructure imports application models, never FastAPI.
- `workers/worker.py` is not the HTTP process and `api/app.py` is not the Kafka
  consumer.
- `main.py` is the only read-API module that combines API and infrastructure.
- All existing worker, snapshot, repository and API tests still pass after the
  import moves.
