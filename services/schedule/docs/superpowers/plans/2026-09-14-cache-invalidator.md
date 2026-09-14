# Cache Invalidator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Invalidate Redis class-schedule cache entries after lesson creation,
rescheduling, and cancellation through the existing Kafka outbox flow.

**Architecture:** Lesson writers create `schedule.changed` outbox events in the
same transaction as their database mutation. The existing outbox relay publishes
them to `schedule.lessons`; a separate long-running Kafka consumer deletes the
affected Redis keys, then commits its offset.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy async, PostgreSQL, Redis 8,
redis-py async, Kafka 4.3, aiokafka, pytest, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-14-cache-invalidator-design.md`

## Global Constraints

- A lesson must start and end on the same calendar date; creation and
  rescheduling reject a midnight-crossing interval with `InvalidLessonInterval`.
- `schedule.changed` payload is `lesson_id`, `class_id`, and ISO date strings
  under `affected_dates`.
- Create and cancel contain one affected date; reschedule contains the distinct
  old and new dates.
- API and migrations must not receive Kafka configuration.
- The invalidator commits Kafka offsets only after Redis invalidation succeeds.

---

### Task 1: Make the one-day lesson rule explicit

**Files:**
- Modify: `src/schedule_service/domain/lesson.py`
- Modify: `tests/test_domain_lesson.py`

**Consumes:** `InvalidLessonInterval`, `Lesson.create`, and `Lesson.reschedule`.

**Produces:** Both creation and rescheduling reject `starts_at.date() !=
ends_at.date()`.

- [ ] **Step 1: Write failing domain tests**

```python
with pytest.raises(InvalidLessonInterval):
    Lesson.create(..., starts_at=sep_10_23_00, ends_at=sep_11_01_00)

with pytest.raises(InvalidLessonInterval):
    lesson.reschedule(starts_at=sep_10_23_00, ends_at=sep_11_01_00)
```

- [ ] **Step 2: Run the focused test**

Run: `poetry run pytest tests/test_domain_lesson.py -q`

Expected: the rescheduling case fails before implementation.

- [ ] **Step 3: Implement one shared interval validator**

```python
@staticmethod
def _validate_interval(starts_at: datetime, ends_at: datetime) -> None:
    if starts_at >= ends_at or starts_at.date() != ends_at.date():
        raise InvalidLessonInterval
```

Call it from both `create` and `reschedule`.

- [ ] **Step 4: Re-run focused tests**

Run: `poetry run pytest tests/test_domain_lesson.py -q`

Expected: PASS.

### Task 2: Record schedule invalidation events with lesson mutations

**Files:**
- Modify: `src/schedule_service/domain/events.py`
- Modify: `src/schedule_service/application/ports/outbox_repository.py`
- Modify: `src/schedule_service/application/create_lesson.py`
- Modify: `src/schedule_service/application/update_lesson.py`
- Modify: `src/schedule_service/application/cancel_lesson.py`
- Modify: `tests/test_create_lesson.py`
- Modify: `tests/test_update_lesson.py`
- Modify: `tests/test_cancel_lesson.py`

**Consumes:** Existing `LessonCreated`, `UnitOfWork.outbox`, and persisted
`Lesson` objects whose `id` is non-null.

**Produces:**

```python
@dataclass(frozen=True, slots=True)
class ScheduleChanged:
    lesson_id: int
    class_id: int
    affected_dates: tuple[date, ...]
```

`OutboxRepository.add` accepts `LessonCreated | ScheduleChanged`.

- [ ] **Step 1: Write failing handler tests**

Assert that creation adds both `LessonCreated` and:

```python
ScheduleChanged(lesson_id=501, class_id=10, affected_dates=(date(2026, 9, 10),))
```

Assert cancellation adds the corresponding one-day `ScheduleChanged`. Assert a
reschedule from 10 September to 11 September adds:

```python
ScheduleChanged(
    lesson_id=501,
    class_id=10,
    affected_dates=(date(2026, 9, 10), date(2026, 9, 11)),
)
```

Update each fake UoW to expose `outbox` with an `events` list.

- [ ] **Step 2: Run handler tests**

Run: `poetry run pytest tests/test_create_lesson.py tests/test_update_lesson.py tests/test_cancel_lesson.py -q`

Expected: FAIL because `ScheduleChanged` and the extra outbox additions do not
exist.

- [ ] **Step 3: Implement the event writes**

In create, add the current `LessonCreated` and then `ScheduleChanged` after
`uow.lessons.add` returns. In update, save `old_day = lesson.starts_at.date()`
before `reschedule`, then use a sorted tuple of `{old_day,
updated_lesson.starts_at.date()}` after successful persistence. In cancel, use
`canceled_lesson.starts_at.date()` after successful persistence. Do not add an
event on not-found or version-conflict paths.

- [ ] **Step 4: Re-run handler tests**

Run: `poetry run pytest tests/test_create_lesson.py tests/test_update_lesson.py tests/test_cancel_lesson.py -q`

Expected: PASS.

### Task 3: Serialize both outbox event types

**Files:**
- Modify: `src/schedule_service/infrastructure/outbox_repository.py`
- Modify: `tests/test_outbox_repository.py`

**Consumes:** `LessonCreated | ScheduleChanged` from the outbox port.

**Produces:** `OutboxEventRow(event_type="schedule.changed", payload=...)`.

- [ ] **Step 1: Write a failing repository test**

Call `repository.add` with:

```python
ScheduleChanged(
    lesson_id=501,
    class_id=10,
    affected_dates=(date(2026, 9, 10), date(2026, 9, 11)),
)
```

Inspect the row passed to `session.add` and assert:

```python
row.event_type == "schedule.changed"
row.payload == {
    "lesson_id": 501,
    "class_id": 10,
    "affected_dates": ["2026-09-10", "2026-09-11"],
}
```

- [ ] **Step 2: Run the test**

Run: `poetry run pytest tests/test_outbox_repository.py -q`

Expected: FAIL because the repository accepts only `LessonCreated`.

- [ ] **Step 3: Implement event-specific mapping**

Keep the existing `LessonCreated` mapping intact. Add a `ScheduleChanged`
branch that stores the payload above. Raise `TypeError` for an unsupported
event type, so new domain events cannot silently disappear.

- [ ] **Step 4: Re-run the test**

Run: `poetry run pytest tests/test_outbox_repository.py -q`

Expected: PASS.

### Task 4: Add cache invalidation to the cache contract

**Files:**
- Modify: `src/schedule_service/application/ports/schedule_cache.py`
- Modify: `src/schedule_service/infrastructure/redis_schedule_cache.py`
- Modify: `tests/test_redis_schedule_cache.py`

**Consumes:** Existing `_key(class_id, day)` and async Redis client.

**Produces:**

```python
async def invalidate(self, *, class_id: int, days: tuple[date, ...]) -> None: ...
```

- [ ] **Step 1: Write failing adapter tests**

For two dates, assert:

```python
client.delete.assert_awaited_once_with(
    "schedule:class:10:date:2026-09-10",
    "schedule:class:10:date:2026-09-11",
)
```

For `days=()`, assert `client.delete.assert_not_called()`.

- [ ] **Step 2: Run focused tests**

Run: `poetry run pytest tests/test_redis_schedule_cache.py -q`

Expected: FAIL because `invalidate` does not exist.

- [ ] **Step 3: Implement the method**

Build keys with `_key`; return immediately for an empty tuple; otherwise call
`await self._client.delete(*keys)`. The returned count is intentionally
ignored: a missing key means cache state is already acceptable.

- [ ] **Step 4: Re-run focused tests**

Run: `poetry run pytest tests/test_redis_schedule_cache.py -q`

Expected: PASS.

### Task 5: Isolate invalidation application logic

**Files:**
- Create: `src/schedule_service/application/cache_invalidator.py`
- Create: `tests/test_cache_invalidator.py`

**Consumes:** `ScheduleChanged` and `ScheduleCache.invalidate`.

**Produces:**

```python
class CacheInvalidator:
    def __init__(self, cache: ScheduleCache) -> None: ...
    async def handle(self, event: ScheduleChanged) -> None: ...
```

- [ ] **Step 1: Write a failing application test**

Use an `AsyncMock` cache. Call `handle` with a two-date event and assert
`invalidate(class_id=10, days=(date(...), date(...)))` was awaited exactly
once.

- [ ] **Step 2: Run the test**

Run: `poetry run pytest tests/test_cache_invalidator.py -q`

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the delegating service**

`handle` passes `event.class_id` and `event.affected_dates` directly to the
cache. It contains no JSON parsing or Kafka calls.

- [ ] **Step 4: Re-run the test**

Run: `poetry run pytest tests/test_cache_invalidator.py -q`

Expected: PASS.

### Task 6: Run the Kafka cache-invalidator worker

**Files:**
- Modify: `src/schedule_service/workers/config.py`
- Create: `src/schedule_service/workers/cache_invalidator.py`
- Modify: `compose.yaml`
- Create: `tests/test_cache_invalidator_worker.py`
- Create: `tests/test_invalidator_config.py`

**Consumes:** `AIOKafkaConsumer`, `RedisScheduleCache`, `CacheInvalidator`,
and `schedule.lessons` envelopes from `KafkaEventPublisher`.

**Produces:** Long-running `python -m schedule_service.workers.cache_invalidator`
process, consuming in group `schedule-cache-invalidator` with
`enable_auto_commit=False`.

- [ ] **Step 1: Write failing configuration and worker tests**

Set `DATABASE_URL`, `KAFKA_BOOTSTRAP_SERVERS`, and `REDIS_URL`; assert
`InvalidatorSettings` exposes only Kafka and Redis values. For the worker,
feed one `schedule.changed` JSON envelope through an async message iterator;
assert cache invalidation occurs before `consumer.commit`. Feed
`lesson.created`; assert it is skipped and committed. Make invalidation raise;
assert `consumer.commit` is not awaited.

- [ ] **Step 2: Run focused tests**

Run: `poetry run pytest tests/test_invalidator_config.py tests/test_cache_invalidator_worker.py -q`

Expected: FAIL with missing modules/classes.

- [ ] **Step 3: Implement settings and the worker**

Define:

```python
class InvalidatorSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    kafka_bootstrap_servers: str
    redis_url: str
```

The worker creates `AIOKafkaConsumer("schedule.lessons", ...,
group_id="schedule-cache-invalidator", enable_auto_commit=False)`, a Redis
client from `settings.redis_url` with `decode_responses=True`, and a
`CacheInvalidator`. For every message: decode JSON; if `event_type` is not
`schedule.changed`, commit and continue; otherwise parse `date.fromisoformat`
for every payload date, handle the event, then commit. In `finally`, stop the
consumer and close the Redis cache. Let malformed `schedule.changed` payloads
and Redis exceptions escape the per-message handler without committing.

Add this Compose service:

```yaml
cache-invalidator:
  build:
    context: .
  env_file:
    - .env
  command:
    - /bin/sh
    - -c
    - >
      KAFKA_BOOTSTRAP_SERVERS="kafka:19092"
      REDIS_URL="redis://redis:6379/0"
      exec poetry run python -m schedule_service.workers.cache_invalidator
  depends_on:
    kafka:
      condition: service_healthy
    redis:
      condition: service_healthy
```

- [ ] **Step 4: Re-run focused tests and Compose validation**

Run: `poetry run pytest tests/test_invalidator_config.py tests/test_cache_invalidator_worker.py -q && docker compose config --quiet`

Expected: tests PASS and Compose prints no validation errors.

### Task 7: Verify the complete behavior

**Files:**
- Modify if needed: tests created in Tasks 1–6 only.

**Consumes:** The complete service stack.

**Produces:** Evidence that a cached read is invalidated after a mutation.

- [ ] **Step 1: Run all automated checks**

Run: `poetry run pytest -q && poetry run ruff check . && poetry run ruff format --check . && docker compose config --quiet`

Expected: all tests pass, Ruff reports no issues, Compose is valid.

- [ ] **Step 2: Run end-to-end Compose verification**

Run: `docker compose up --build -d && docker compose ps`

Expected: `postgres`, `kafka`, `redis`, `api`, `outbox-relay`, and
`cache-invalidator` are running; migrations exited with code 0.

- [ ] **Step 3: Verify cache invalidation**

Create or choose a lesson. GET its class/day schedule to populate Redis. Check
the corresponding `schedule:class:<id>:date:<day>` key exists with
`docker compose exec redis redis-cli GET <key>`. PATCH the lesson to a different
time or day. Poll Redis until the old key is absent, then GET the schedule again
and verify Redis contains rebuilt JSON.

- [ ] **Step 4: Commit the feature**

```bash
git add src/schedule_service tests compose.yaml docs/superpowers
git commit -m "feat: invalidate cached schedules from Kafka events"
```
