# Analytics read API

## Goal

Expose the current daily workload calculated by the analytics service through
an independent HTTP API. It answers one question:

> What planned workload does analytics currently report for one class on one
> calendar day?

The API reads ClickHouse only. It never calls Schedule or writes to Schedule
PostgreSQL.

## Boundaries

The analytics project has two independent long-running processes built from the
same Docker image:

| Process | Responsibility | Must not do |
| --- | --- | --- |
| `analytics` | Consume Kafka snapshots and persist analytical history in ClickHouse | Serve HTTP requests |
| `analytics-api` | Read the calculated workload from ClickHouse and return HTTP responses | Consume Kafka or write Schedule data |

Schedule remains the source of truth for the current lesson list. The workload
API is eventually consistent: a response can lag a successful schedule command
by up to the materialized-view refresh interval.

## HTTP contract

### `GET /workload`

Required query parameters:

- `class_id`: positive integer;
- `day`: ISO-8601 calendar date, for example `2026-10-02`.

A matching row returns `200 OK`:

```json
{
  "class_id": 9021,
  "day": "2026-10-02",
  "planned_lessons_count": 1,
  "planned_minutes": 60,
  "refreshed_at": "2026-09-19T00:08:00Z"
}
```

If `class_daily_workload` has no row for the requested class and day, the API
returns `404 Not Found`. A missing row deliberately does not claim that the
workload is zero: the materialized view may not yet have refreshed after a
schedule change.

If ClickHouse is unavailable or its workload query fails, the API returns
`503 Service Unavailable` with a stable public detail message. It must not
return database internals.

### `GET /health/live`

Returns `200 OK` while the analytics API process is alive. This endpoint is a
liveness check only and intentionally does not connect to ClickHouse.

## Components

### Settings

`AnalyticsApiSettings` contains ClickHouse-only connection values:

- `clickhouse_host`;
- `clickhouse_port`;
- `clickhouse_user`;
- `clickhouse_password`.

Worker-only Kafka settings remain in `AnalyticsSettings`; the read API does not
accept or depend on Kafka configuration.

### Workload repository

`application/ports/workload_repository.py` defines the `WorkloadRepository`
protocol (контракт репозитория). The API depends only on this protocol. The
`ClassDailyWorkload` read model lives in `application/workload.py`.

`infrastructure/clickhouse_workload_repository.py` provides the concrete
`ClickHouseWorkloadRepository` adapter. It receives the synchronous
`clickhouse_connect` client and delegates the blocking query to
`asyncio.to_thread`, returning a workload value object or `None`.

The query selects exactly one row from `class_daily_workload` by `class_id` and
`day`. It returns only the five public workload columns.

### FastAPI application

`api/app.py` exposes an application factory constructed with settings and a
factory returning `WorkloadRepository`, so endpoint tests can supply a fake
without importing infrastructure. `main.py` creates the real ClickHouse
client, constructs the adapter, and imports the Uvicorn `app`. This keeps test
application construction free of import-time network I/O. The route validates
HTTP input, obtains one repository instance, and maps outcomes as follows:

| Repository outcome | HTTP response |
| --- | --- |
| Workload value | 200 with JSON response |
| `None` | 404 |
| ClickHouse exception | 503 |

### Project structure

The analytics service follows the same dependency direction as Schedule:

```text
api / workers  ->  application (read models and ports)
infrastructure ->  application
main           ->  api + infrastructure
```

The existing worker code moves into the same structure: snapshot data and its
parser go to `application/snapshot.py`; ClickHouse adapters go to
`infrastructure/`; the Kafka process entry point goes to `workers/worker.py`.
This is a structural refactor only: Kafka and ClickHouse behaviour stays the
same.

## Runtime topology

Compose adds `analytics-api`:

- build context: `./services/analytics`;
- command: `poetry run uvicorn analytics_service.main:app --host 0.0.0.0 --port 8000`;
- host port: `8001:8000`;
- reads the same ignored `.clickhouse.env` credentials file as ClickHouse and
  the analytics worker;
- depends only on healthy ClickHouse;
- uses `restart: unless-stopped`;
- has an HTTP liveness healthcheck against `/health/live`.

`analytics-api` must not depend on Kafka, Schedule API, migrations, or
PostgreSQL. No existing service depends on `analytics-api`.

## Verification

Unit tests cover:

- ClickHouse repository query construction and row-to-value-object mapping;
- no-row mapping to `None`;
- `GET /workload` responses for 200, 404 and 503;
- query parameter validation;
- liveness without ClickHouse access;
- API settings environment loading.

Compose verification confirms the API container becomes healthy, and a live
request for the end-to-end workload fixture returns the materialized-view
result.

## Explicit non-goals

- Writing lesson data or calling Schedule from analytics API.
- A dashboard, charts, pagination, or date ranges.
- Kafka consumer management from the HTTP process.
- A readiness endpoint that calls ClickHouse.
- Teacher- or subject-level workload endpoints.
