# Analytics Read API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the current class-day workload from ClickHouse through an
independent analytics HTTP API.

**Architecture:** Add a FastAPI process to the existing analytics project. It
uses a small repository adapter around the synchronous ClickHouse client,
offloading the query with `asyncio.to_thread`; the worker and API remain
separate Compose services built from the same image.

**Tech Stack:** Python 3.14, FastAPI, Uvicorn, clickhouse-connect 1.8.x,
Pydantic Settings, Docker Compose, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-19-analytics-read-api-design.md`

## Global Constraints

- Analytics API reads only `class_daily_workload` from ClickHouse.
- It never consumes Kafka, calls Schedule, or writes Schedule PostgreSQL data.
- `GET /workload` has required positive `class_id` and ISO date `day` query
  parameters.
- A matching workload returns 200; a missing row returns 404; ClickHouse query
  failure returns 503 without database internals.
- `/health/live` is liveness only and must not connect to ClickHouse.
- `analytics-api` is independent of Kafka, Schedule API, migrations and
  PostgreSQL; it depends only on healthy ClickHouse.
- Use `asyncio.to_thread` around all synchronous clickhouse-connect I/O.
- Keep Ruff target Python 3.14 and line length 88.

## Review Focus

- `class_id=0` and negative `class_id` must be rejected by FastAPI validation
  before a repository query.
- Invalid `day` text must be rejected with 422 rather than becoming a
  ClickHouse query.
- A no-row ClickHouse response is 404, not a misleading zero workload.
- A ClickHouse exception maps to a stable 503 response and does not expose the
  exception message.
- `/health/live` must remain 200 even if the repository would fail, because it
  is liveness rather than readiness.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `services/analytics/src/analytics_service/workload.py` | Immutable workload value object returned by repository and API |
| `services/analytics/src/analytics_service/workload_repository.py` | ClickHouse query and row mapping adapter |
| `services/analytics/src/analytics_service/config.py` | Add `AnalyticsApiSettings`; leave worker settings intact |
| `services/analytics/src/analytics_service/app.py` | FastAPI application factory, routes and HTTP error mapping |
| `services/analytics/src/analytics_service/main.py` | Real ClickHouse client and Uvicorn `app` composition |
| `services/analytics/tests/test_workload_repository.py` | Adapter query, mapping and no-row tests |
| `services/analytics/tests/test_api.py` | HTTP contract, validation and liveness tests |
| `services/analytics/tests/test_config.py` | API settings environment test |
| `services/analytics/pyproject.toml` | FastAPI/Uvicorn runtime and HTTP test dependency |
| `services/analytics/poetry.lock` | Locked resolved dependencies |
| `compose.yaml` | `analytics-api` runtime service and liveness healthcheck |

### Task 1: Add workload value and ClickHouse read adapter

**Files:**
- Create: `services/analytics/src/analytics_service/workload.py`
- Create: `services/analytics/src/analytics_service/workload_repository.py`
- Create: `services/analytics/tests/test_workload_repository.py`

**Interfaces:**
- Consumes: `clickhouse_connect.driver.Client` and existing
  `class_daily_workload` columns.
- Produces:

```python
@dataclass(frozen=True, slots=True)
class ClassDailyWorkload:
    class_id: int
    day: date
    planned_lessons_count: int
    planned_minutes: int
    refreshed_at: datetime


class ClickHouseWorkloadRepository:
    def __init__(self, client: Client) -> None: ...

    async def get(self, *, class_id: int, day: date) -> ClassDailyWorkload | None: ...
```

- [ ] **Step 1: Write failing repository tests**

```python
@pytest.mark.anyio
async def test_repository_returns_workload_for_one_class_and_day() -> None:
    client = Mock()
    client.query.return_value = SimpleNamespace(
        result_rows=[(10, date(2026, 10, 2), 1, 60, datetime(2026, 9, 19, tzinfo=UTC))]
    )
    repository = ClickHouseWorkloadRepository(client)

    result = await repository.get(class_id=10, day=date(2026, 10, 2))

    assert result == ClassDailyWorkload(
        class_id=10,
        day=date(2026, 10, 2),
        planned_lessons_count=1,
        planned_minutes=60,
        refreshed_at=datetime(2026, 9, 19, tzinfo=UTC),
    )
    client.query.assert_called_once_with(
        """
        SELECT class_id, day, planned_lessons_count, planned_minutes, refreshed_at
        FROM class_daily_workload
        WHERE class_id = {class_id:UInt64} AND day = {day:Date}
        LIMIT 1
        """,
        parameters={"class_id": 10, "day": date(2026, 10, 2)},
    )


@pytest.mark.anyio
async def test_repository_returns_none_when_workload_row_is_missing() -> None:
    client = Mock()
    client.query.return_value = SimpleNamespace(result_rows=[])

    result = await ClickHouseWorkloadRepository(client).get(
        class_id=10, day=date(2026, 10, 2)
    )

    assert result is None
```

- [ ] **Step 2: Run the tests to verify RED**

Run: `poetry run pytest tests/test_workload_repository.py -q`

Expected: FAIL with `ModuleNotFoundError` for `analytics_service.workload`.

- [ ] **Step 3: Implement the value object and repository**

```python
# workload.py
from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class ClassDailyWorkload:
    class_id: int
    day: date
    planned_lessons_count: int
    planned_minutes: int
    refreshed_at: datetime
```

```python
# workload_repository.py
import asyncio
from datetime import date

from clickhouse_connect.driver import Client

from analytics_service.workload import ClassDailyWorkload


class ClickHouseWorkloadRepository:
    def __init__(self, client: Client) -> None:
        self._client = client

    async def get(self, *, class_id: int, day: date) -> ClassDailyWorkload | None:
        result = await asyncio.to_thread(
            self._client.query,
            """
            SELECT class_id, day, planned_lessons_count, planned_minutes, refreshed_at
            FROM class_daily_workload
            WHERE class_id = {class_id:UInt64} AND day = {day:Date}
            LIMIT 1
            """,
            parameters={"class_id": class_id, "day": day},
        )
        if not result.result_rows:
            return None

        class_id, day, count, minutes, refreshed_at = result.result_rows[0]
        return ClassDailyWorkload(
            class_id=class_id,
            day=day,
            planned_lessons_count=count,
            planned_minutes=minutes,
            refreshed_at=refreshed_at,
        )
```

- [ ] **Step 4: Run focused checks**

Run:

```bash
poetry run pytest tests/test_workload_repository.py -q
poetry run ruff check .
poetry run ruff format --check .
```

Expected: all pass.

- [ ] **Step 5: Commit the adapter**

```bash
git add services/analytics/src/analytics_service/workload.py \
  services/analytics/src/analytics_service/workload_repository.py \
  services/analytics/tests/test_workload_repository.py
git commit -m "feat: add analytics workload repository"
```

### Task 2: Add FastAPI application and HTTP contract

**Files:**
- Modify: `services/analytics/pyproject.toml`
- Modify: `services/analytics/poetry.lock`
- Modify: `services/analytics/src/analytics_service/config.py`
- Create: `services/analytics/src/analytics_service/app.py`
- Create: `services/analytics/src/analytics_service/main.py`
- Create: `services/analytics/tests/test_api.py`
- Modify: `services/analytics/tests/test_config.py`

**Interfaces:**
- Consumes: `ClassDailyWorkload`, `ClickHouseWorkloadRepository` and
  ClickHouse connection values.
- Produces:

```python
class AnalyticsApiSettings(BaseSettings):
    clickhouse_host: str
    clickhouse_port: int
    clickhouse_user: str
    clickhouse_password: str


def create_app(
    settings: AnalyticsApiSettings,
    repository_factory: Callable[[], ClickHouseWorkloadRepository],
) -> FastAPI: ...
```

- [ ] **Step 1: Add FastAPI dependencies and lock them**

Add runtime dependencies in `pyproject.toml`:

```toml
"fastapi (>=0.115.0,<1.0.0)",
"uvicorn (>=0.34.0,<1.0.0)",
```

Add the HTTP test client in development dependencies:

```toml
"httpx (>=0.28.0,<1.0.0)",
```

Run:

```bash
poetry lock
poetry install
```

- [ ] **Step 2: Write failing HTTP and settings tests**

Use a fake repository with `async def get(...)` returning a workload or
raising an exception. Cover all review-focus cases:

```python
def test_get_workload_returns_materialized_result() -> None:
    app = create_app(settings, repository_factory=lambda: FakeRepository(result))
    with TestClient(app) as client:
        response = client.get("/workload", params={"class_id": 10, "day": "2026-10-02"})

    assert response.status_code == 200
    assert response.json() == {
        "class_id": 10,
        "day": "2026-10-02",
        "planned_lessons_count": 1,
        "planned_minutes": 60,
        "refreshed_at": "2026-09-19T00:00:00Z",
    }


def test_get_workload_returns_404_when_row_is_missing() -> None:
    app = create_app(settings, repository_factory=lambda: FakeRepository(None))
    with TestClient(app) as client:
        response = client.get("/workload", params={"class_id": 10, "day": "2026-10-02"})

    assert response.status_code == 404


def test_get_workload_returns_503_when_clickhouse_fails() -> None:
    app = create_app(settings, repository_factory=lambda: FailingRepository())
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/workload", params={"class_id": 10, "day": "2026-10-02"})

    assert response.status_code == 503
    assert response.json() == {"detail": "Analytics storage is unavailable"}


def test_get_workload_rejects_non_positive_class_id() -> None:
    with TestClient(app) as client:
        response = client.get("/workload", params={"class_id": 0, "day": "2026-10-02"})
    assert response.status_code == 422


def test_get_workload_rejects_invalid_day() -> None:
    with TestClient(app) as client:
        response = client.get("/workload", params={"class_id": 10, "day": "not-a-date"})
    assert response.status_code == 422


def test_live_endpoint_does_not_create_repository() -> None:
    repository_factory = Mock()
    app = create_app(settings, repository_factory)
    with TestClient(app) as client:
        response = client.get("/health/live")
    assert response.status_code == 200
    repository_factory.assert_not_called()
```

Add a config test that sets only `CLICKHOUSE_HOST`, `CLICKHOUSE_PORT`,
`CLICKHOUSE_USER` and `CLICKHOUSE_PASSWORD`, then asserts
`AnalyticsApiSettings()` reads each value.

- [ ] **Step 3: Run the tests to verify RED**

Run: `poetry run pytest tests/test_api.py tests/test_config.py -q`

Expected: FAIL because FastAPI and `analytics_service.app` are not yet present.

- [ ] **Step 4: Implement API configuration and routes**

Keep the existing worker `AnalyticsSettings` unchanged. Add this class to
`config.py`:

```python
class AnalyticsApiSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    clickhouse_host: str
    clickhouse_port: int
    clickhouse_user: str
    clickhouse_password: str
```

Implement `app.py` using `Annotated[int, Query(gt=0)]` and `date`:

```python
def create_app(
    settings: AnalyticsApiSettings,
    repository_factory: Callable[[], ClickHouseWorkloadRepository],
) -> FastAPI:
    app = FastAPI()

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/workload")
    async def get_workload(
        class_id: Annotated[int, Query(gt=0)], day: date
    ) -> ClassDailyWorkload:
        try:
            workload = await repository_factory().get(class_id=class_id, day=day)
        except Exception as exc:
            raise HTTPException(
                status_code=503, detail="Analytics storage is unavailable"
            ) from exc
        if workload is None:
            raise HTTPException(status_code=404, detail="Workload was not found")
        return workload

    return app
```

In `main.py`, construct the real client and factory so Uvicorn can import
`analytics_service.main:app`:

```python
settings = AnalyticsApiSettings()
client = clickhouse_connect.get_client(
    host=settings.clickhouse_host,
    port=settings.clickhouse_port,
    username=settings.clickhouse_user,
    password=settings.clickhouse_password,
)
app = create_app(settings, lambda: ClickHouseWorkloadRepository(client))
```

- [ ] **Step 5: Run focused checks**

Run:

```bash
poetry run pytest tests/test_api.py tests/test_config.py -q
poetry run ruff check .
poetry run ruff format --check .
```

Expected: all pass.

- [ ] **Step 6: Commit the API contract**

```bash
git add services/analytics/pyproject.toml services/analytics/poetry.lock \
  services/analytics/src/analytics_service/config.py \
  services/analytics/src/analytics_service/app.py \
  services/analytics/src/analytics_service/main.py \
  services/analytics/tests/test_api.py services/analytics/tests/test_config.py
git commit -m "feat: add analytics workload API"
```

### Task 3: Run analytics API in Compose and prove live read

**Files:**
- Modify: `compose.yaml`
- Modify: `services/analytics/tests/test_api.py`

**Interfaces:**
- Consumes: `analytics_service.main:app`, `.clickhouse.env`, ClickHouse service.
- Produces: a healthy HTTP service on `http://127.0.0.1:8001`.

- [ ] **Step 1: Add a Compose assertion test**

Add a text-level test that reads root `compose.yaml` and asserts it has an
`analytics-api` service with `8001:8000`, the analytics build context, the
credentials `env_file`, a healthy ClickHouse dependency, `restart:
unless-stopped`, and a liveness healthcheck that calls
`http://127.0.0.1:8000/health/live`.

- [ ] **Step 2: Run the test to verify RED**

Run: `poetry run pytest tests/test_api.py -q`

Expected: FAIL because `analytics-api` is absent from Compose.

- [ ] **Step 3: Add the independent `analytics-api` service**

```yaml
  analytics-api:
    build:
      context: ./services/analytics
    env_file:
      - ./services/analytics/.clickhouse.env
    environment:
      CLICKHOUSE_HOST: clickhouse
      CLICKHOUSE_PORT: 8123
    command:
      - poetry
      - run
      - uvicorn
      - analytics_service.main:app
      - --host
      - 0.0.0.0
      - --port
      - "8000"
    ports:
      - "8001:8000"
    depends_on:
      clickhouse:
        condition: service_healthy
    restart: unless-stopped
    healthcheck:
      test:
        [
          "CMD",
          "python",
          "-c",
          "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/health/live')",
        ]
      interval: 5s
      timeout: 3s
      retries: 5
      start_period: 5s
```

- [ ] **Step 4: Run focused checks**

Run:

```bash
poetry -C services/analytics run pytest tests/test_api.py -q
docker compose config --quiet
poetry -C services/analytics run ruff check .
poetry -C services/analytics run ruff format --check .
```

Expected: all pass.

- [ ] **Step 5: Prove the container and endpoint**

Run:

```bash
docker compose up --build -d analytics-api
docker compose ps analytics-api
curl -i http://127.0.0.1:8001/health/live
curl -i "http://127.0.0.1:8001/workload?class_id=9021&day=2026-10-02"
curl -i "http://127.0.0.1:8001/workload?class_id=9021&day=2026-10-03"
```

Expected: the container is healthy; liveness is 200; the known workload is
200 with `1` and `60`; the absent day is 404.

- [ ] **Step 6: Commit runtime topology**

```bash
git add compose.yaml services/analytics/tests/test_api.py
git commit -m "feat: run analytics workload API"
```

## Final Verification

- [ ] **Step 1: Run every automated check**

```bash
poetry -C services/schedule run pytest -q
poetry -C services/schedule run ruff check .
poetry -C services/schedule run ruff format --check .
poetry -C services/analytics run pytest -q
poetry -C services/analytics run ruff check .
poetry -C services/analytics run ruff format --check .
docker compose config --quiet
git diff --check
```

Expected: all checks pass.

- [ ] **Step 2: Review the end-to-end response**

Confirm `GET /workload` returns the materialized ClickHouse value, not a
Schedule/PostgreSQL read, by querying a class-day created in the previous
analytics verification.

## Plan Self-Review

- Spec coverage: Tasks 1-3 cover the value, ClickHouse read, 200/404/503,
  liveness, settings, Compose topology and live verification. No requirement
  is uncovered.
- Placeholder scan: no TODO/TBD or generic error-handling instructions remain.
- Type consistency: `ClassDailyWorkload`, `ClickHouseWorkloadRepository.get`,
  `AnalyticsApiSettings` and `create_app` use the same names in all tasks.
- Review focus: every listed boundary has an explicit test in Task 2, except
  the live-container configuration, which Task 3 verifies.
