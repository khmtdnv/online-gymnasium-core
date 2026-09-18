# Analytics Workload Service Implementation Plan

> **For agentic workers:** Use task-by-task execution. Steps use checkbox syntax for tracking.

**Goal:** Build an independent analytics consumer which stores lesson snapshots
in ClickHouse and refreshes current daily workload for classes every minute.

**Architecture:** Schedule writes a complete lesson snapshot into its
transactional outbox after create, reschedule and cancel. Its existing relay
publishes that snapshot to Kafka. Analytics consumes in a separate group,
stores immutable snapshots in ClickHouse, and a refreshable view rebuilds the
class-day workload from the latest lesson version.

**Tech Stack:** Python 3.14, Poetry 2.3.4, aiokafka 0.14.x,
clickhouse-connect 1.8.x, Kafka 4.3.1, ClickHouse 26.8, Docker Compose,
pytest and Ruff.

**Spec:** docs/superpowers/specs/2026-09-18-analytics-service-design.md

## Global Constraints

- Schedule owns lessons. Analytics never writes schedule PostgreSQL data.
- Kafka topic is schedule.lessons and analytics group is schedule-analytics.
- Kafka delivery is at least once; a duplicate event changes no logical result.
- The only workload metric is class_id plus day, planned lesson count, planned
  minutes and refreshed_at.
- Analytics may lag by one minute. It is not the live schedule read source.
- The learner writes production code and Compose. Codex writes tests, checks
  RED and GREEN, reviews, verifies and commits.

## File structure

| Path | Responsibility |
|---|---|
| services/schedule/src/schedule_service/domain/events.py | LessonSnapshot domain event |
| services/schedule/src/schedule_service/application/create_lesson.py | Emits snapshot after create |
| services/schedule/src/schedule_service/application/update_lesson.py | Emits snapshot after reschedule |
| services/schedule/src/schedule_service/application/cancel_lesson.py | Emits snapshot after cancel |
| services/schedule/src/schedule_service/infrastructure/outbox_repository.py | Maps snapshot to lesson.snapshot row |
| services/analytics/pyproject.toml | Analytics dependencies and tooling |
| services/analytics/sql/001_schema.sql | ClickHouse tables and refreshable view |
| services/analytics/src/analytics_service/snapshot.py | Envelope parser and value object |
| services/analytics/src/analytics_service/clickhouse_repository.py | ClickHouse insertion adapter |
| services/analytics/src/analytics_service/config.py | Worker-only settings |
| services/analytics/src/analytics_service/worker.py | Consumer lifecycle and offset commits |
| services/schedule/compose.yaml | ClickHouse and analytics services |

### Task 1: Add lesson snapshot outbox events

**Files:** events.py, create_lesson.py, update_lesson.py, cancel_lesson.py,
outbox repository port and adapter; create/update/cancel/outbox tests.

**Interface produced:** LessonSnapshot has lesson_id, class_id, starts_at,
ends_at, status and version. The outbox adapter maps it to event type
lesson.snapshot and an ISO JSON payload with those fields.

- [ ] Codex writes failing tests. Each successful create, reschedule and cancel
  must add one LessonSnapshot with the persisted result. Update asserts new
  time/version; cancel asserts cancelled status.
- [ ] Codex runs targeted schedule tests and confirms RED.
- [ ] Learner adds LessonSnapshot and accepts it in the outbox protocol/adapter.
- [ ] Learner emits it after every successful persistence and before UoW exit.
  ScheduleChanged remains unchanged for cache invalidation.
- [ ] Codex runs targeted tests, full schedule Ruff checks and commits
  feat: publish lesson snapshots for analytics.

### Task 2: Scaffold analytics and ClickHouse

**Files:** create services/analytics with Poetry project, Dockerfile,
dockerignore, package init and test config; modify schedule Compose.

**Interface produced:** analytics accepts KAFKA_BOOTSTRAP_SERVERS,
CLICKHOUSE_HOST and CLICKHOUSE_PORT. Compose exposes ClickHouse HTTP at host
8123 and service hostname clickhouse.

- [ ] Learner creates an independent Poetry project for Python 3.14 with
  aiokafka, clickhouse-connect and pydantic-settings as main dependencies,
  pytest and Ruff as development dependencies.
- [ ] Learner creates a Dockerfile using the same Poetry and Python conventions
  as schedule.
- [ ] Learner adds clickhouse using image clickhouse/clickhouse-server:26.8,
  persistent clickhouse_data and a SELECT 1 healthcheck.
- [ ] Learner adds analytics depending only on healthy Kafka and ClickHouse,
  with restart unless stopped. Do not add analytics dependencies to API or
  migrations.
- [ ] Codex verifies Poetry, Ruff, Compose and a healthy ClickHouse container,
  then commits chore: add analytics service and ClickHouse.

### Task 3: Add ClickHouse schema

**Files:** create services/analytics/sql/001_schema.sql and test_schema.py.

**Interface produced:** lesson_snapshots stores event_id, occurred_at,
lesson_id, class_id, starts_at, ends_at, status and version in append-only
MergeTree storage. class_daily_workload stores class_id, day, planned count,
planned minutes and refreshed_at.

- [ ] Codex writes a failing schema contract test for both tables, a materialized
  view named class_daily_workload_mv, REFRESH EVERY 1 MINUTE, latest-version
  selection, planned filtering and duration aggregation.
- [ ] Learner writes schema SQL. The view derives one latest snapshot per
  lesson using its greatest version, then groups planned lessons by class and
  start date and sums their minute duration. It atomically replaces the target.
- [ ] Codex starts a fresh ClickHouse volume, confirms all schema objects exist
  and commits feat: add analytics workload materialized view.

### Task 4: Parse and persist Kafka snapshots

**Files:** create snapshot.py, clickhouse_repository.py, test_snapshot.py and
test_clickhouse_repository.py.

**Interface produced:** parse_lesson_snapshot returns a LessonSnapshot or None
for an unrelated event. ClickHouseSnapshotRepository.add stores exactly one
row in lesson_snapshots.

- [ ] Codex writes RED tests for a valid lesson.snapshot envelope, unrelated
  schedule.changed event, malformed snapshot and insert column/value mapping.
- [ ] Learner parses ISO dates, preserves Kafka envelope event_id and rejects
  missing required snapshot values.
- [ ] Learner uses clickhouse-connect client insertion via asyncio.to_thread,
  so synchronous I/O cannot block the Kafka event loop.
- [ ] Codex verifies parser/repository tests and commits
  feat: add analytics snapshot ingestion.

### Task 5: Add consumer worker

**Files:** create config.py, worker.py and test_worker.py; modify Compose
analytics command.

**Interface produced:** AnalyticsSettings reads worker-only Kafka/ClickHouse
settings. run starts AIOKafkaConsumer with auto commits disabled, topic
schedule.lessons, group schedule-analytics and earliest offset reset.

- [ ] Codex writes RED worker tests: insert happens before commit; unrelated
  events are committed after deliberate ignore; insertion failure does not
  commit; settings read environment values.
- [ ] Learner composes consumer, ClickHouse client and repository. It commits
  an offset only after successful insertion or known-event ignore. On error it
  logs and raises, leaving the offset uncommitted for retry.
- [ ] Learner sets the Compose command to run the module worker.
- [ ] Codex verifies analytics tests and Ruff, Compose configuration and commits
  feat: consume lesson snapshots into analytics.

### Task 6: Prove end-to-end behaviour

**Files:** no planned production changes; add a regression test only if live
verification reveals a contract gap.

- [ ] Codex starts the full Compose stack.
- [ ] Codex creates a fresh planned lesson, waits one view refresh, and queries
  ClickHouse for one class-day count and duration.
- [ ] Codex reschedules the lesson to another day, waits one refresh and
  verifies the old day loses its contribution while the new day gains it.
- [ ] Codex runs full schedule and analytics pytest/Ruff suites plus Compose
  validation and reports exact evidence.
