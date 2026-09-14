# Schedule Cache Lock and Generation Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent cache stampedes and stale cache repopulation after Kafka invalidation for a class-day schedule.

**Architecture:** The application handler coordinates cache-aside reads through a token-based Redis fill lock. `RedisScheduleCache` owns Redis key layout, serialization, and three atomic Lua operations: safe lock release, generation-guarded set, and generation increment plus deletion. The Kafka invalidator keeps its current shape and calls the strengthened `invalidate` operation.

**Tech Stack:** Python 3.14, FastAPI, Pydantic Settings, redis-py asyncio, Redis Lua, SQLAlchemy async, pytest.

**Spec:** `docs/superpowers/specs/2026-09-15-schedule-cache-lock-generation-design.md`

## Global Constraints

- Use one Redis instance; do not add multi-node Redlock or another dependency.
- Generate an ownership token with `secrets.token_urlsafe(32)`.
- Use `SET ... NX PX` for a fill lock; default lock TTL is exactly 5000 ms.
- An owner may delete a lock only after Lua verifies that its token still matches.
- Treat a missing generation key as integer `0`; generation keys do not expire in this slice.
- Cache data TTL is 60 seconds; waiters retry every 50 ms for at most 20 attempts by default.
- On exhausted retries raise an application error and return HTTP 503. Do not fall back to an uncoordinated database read.
- Never import `redis` or Redis types into `application/` or `domain/`.
- Keep all Python lines at 88 characters or fewer.

---

## File structure

| File | Responsibility |
| --- | --- |
| `src/schedule_service/config.py` | API cache coordination settings and defaults. |
| `src/schedule_service/application/errors.py` | Named application error for bounded lock wait exhaustion. |
| `src/schedule_service/application/ports/schedule_cache.py` | Redis-agnostic cache coordination contract. |
| `src/schedule_service/infrastructure/redis_schedule_cache.py` | Key naming, JSON mapping, Redis commands, and Lua scripts. |
| `src/schedule_service/application/list_lessons.py` | Read protocol, retry loop, UoW database read, and conditional cache fill. |
| `src/schedule_service/app.py` | Makes validated settings available to dependencies. |
| `src/schedule_service/api/dependencies.py` | Injects cache configuration into `ListLessonsHandler`. |
| `src/schedule_service/api/lessons.py` | Maps bounded cache-fill exhaustion to HTTP 503. |
| `tests/test_redis_schedule_cache.py` | Agent-owned adapter tests for keys, scripts, locking, and generation. |
| `tests/test_list_lessons.py` | Agent-owned handler tests for concurrent protocol behavior. |
| `tests/test_lessons.py` | Agent-owned HTTP 503 test. |

## Production work — learner

### Task 1: Introduce cache coordination configuration and error

**Files:**
- Modify: `src/schedule_service/config.py`
- Modify: `src/schedule_service/application/errors.py`

**Produces:**
- `Settings.schedule_cache_ttl_seconds: int = 60`
- `Settings.schedule_cache_lock_ttl_ms: int = 5000`
- `Settings.schedule_cache_lock_retry_delay_ms: int = 50`
- `Settings.schedule_cache_lock_retry_limit: int = 20`
- `ScheduleCacheBusy(ApplicationException)`

- [ ] Add the four positive integer settings to `Settings`. Their defaults must
  exactly match the values above; environment variables use Pydantic's usual
  uppercase mapping. Import `Field` from `pydantic` and write them as:

```python
schedule_cache_ttl_seconds: int = Field(default=60, gt=0)
schedule_cache_lock_ttl_ms: int = Field(default=5000, gt=0)
schedule_cache_lock_retry_delay_ms: int = Field(default=50, gt=0)
schedule_cache_lock_retry_limit: int = Field(default=20, gt=0)
```
- [ ] Add `ScheduleCacheBusy` to `application/errors.py`. It means the handler
  could not obtain a cache result or fill lock within the bounded retry budget.
- [ ] Do not change `.env.example`: defaults are sufficient for local startup.

### Task 2: Expand the cache port without Redis coupling

**Files:**
- Modify: `src/schedule_service/application/ports/schedule_cache.py`

**Consumes:** existing `get`, `aclose`, and `invalidate` contract.

**Produces:**

```python
async def get_generation(self, *, class_id: int, day: date) -> int: ...


async def try_acquire_fill_lock(
    self,
    *,
    class_id: int,
    day: date,
    token: str,
    ttl_ms: int,
) -> bool: ...


async def release_fill_lock(self, *, class_id: int, day: date, token: str) -> None: ...


async def set_if_generation(
    self,
    *,
    class_id: int,
    day: date,
    lessons: list[Lesson],
    ttl_seconds: int,
    expected_generation: int,
) -> bool: ...
```

- [ ] Remove the old unconditional `set(...)` operation. A caller may only
  populate this cache with `set_if_generation(...)`.
- [ ] Keep `invalidate(class_id, days)` unchanged at the port boundary: callers
  must not know that it also changes generation.

### Task 3: Implement Redis keys and atomic adapter primitives

**Files:**
- Modify: `src/schedule_service/infrastructure/redis_schedule_cache.py`

**Consumes:** Task 2 contract.

**Produces:** an adapter that has these private key helpers:

```python
def _key(self, *, class_id: int, day: date) -> str: ...
def _generation_key(self, *, class_id: int, day: date) -> str: ...
def _lock_key(self, *, class_id: int, day: date) -> str: ...
```

- [ ] Retain `_key()` exactly as the current data-key format.
- [ ] Return `f"{self._key(...)}:gen"` from `_generation_key()` and
  `f"{self._key(...)}:lock"` from `_lock_key()`.
- [ ] Extract current lesson-to-dict serialization into a private helper so
  `set_if_generation()` passes one JSON string to Redis.
- [ ] Implement `get_generation()` with `GET generation-key`; return `0` for
  `None`, otherwise `int(value)`.
- [ ] Implement `try_acquire_fill_lock()` with:

```python
result = await self._client.set(lock_key, token, nx=True, px=ttl_ms)
return result is True
```

- [ ] Implement `release_fill_lock()` using `EVAL` and this script:

```lua
if redis.call("GET", KEYS[1]) == ARGV[1] then
  return redis.call("DEL", KEYS[1])
end
return 0
```

  Call it with one key and the token. Ignore its numeric return value.
- [ ] Implement `set_if_generation()` using `EVAL` with data key as `KEYS[1]`,
  generation key as `KEYS[2]`, expected generation as `ARGV[1]`, serialized
  JSON as `ARGV[2]`, and TTL seconds as `ARGV[3]`:

```lua
local current = redis.call("GET", KEYS[2]) or "0"
if current ~= ARGV[1] then
  return 0
end
redis.call("SET", KEYS[1], ARGV[2], "EX", ARGV[3])
return 1
```

  Pass `str(expected_generation)` and `str(ttl_seconds)` as the corresponding
  arguments and return `bool(result)` from Python.
- [ ] Replace the old multi-key `delete` in `invalidate()` with one `EVAL` per
  day. Each script must run `INCR generation-key` before `DEL data-key`:

```lua
redis.call("INCR", KEYS[2])
return redis.call("DEL", KEYS[1])
```

  An empty `days` tuple still must not call Redis.

### Task 4: Replace simple cache-aside with the guarded fill protocol

**Files:**
- Modify: `src/schedule_service/application/list_lessons.py`

**Consumes:** Task 1 settings, Task 2 cache port, and existing UoW factory.

**Produces:** `ListLessonsHandler` that does at most one direct database query
per successfully coalesced cache fill.

- [ ] Add constructor parameters for all four cache settings. Store them on the
  handler. Keep names identical to `Settings` fields:

```python
def __init__(
    self,
    uow_factory: UnitOfWorkFactory,
    cache: ScheduleCache,
    schedule_cache_ttl_seconds: int,
    schedule_cache_lock_ttl_ms: int,
    schedule_cache_lock_retry_delay_ms: int,
    schedule_cache_lock_retry_limit: int,
) -> None: ...
```
- [ ] Add a private `_read_from_database(query)` method containing the existing
  `async with self._uow_factory()` and repository call. It returns
  `list[Lesson]`.
- [ ] In `handle()`, retain the initial `cache.get(...)` fast path.
- [ ] For each attempt in `range(self._schedule_cache_lock_retry_limit)`, first
  call `cache.get(...)` and return on a hit. On a miss, create a fresh token
  with `secrets.token_urlsafe(32)` and try the fill lock.
- [ ] If the lock is unavailable, `await asyncio.sleep(
  self._schedule_cache_lock_retry_delay_ms / 1000)` and continue the loop.
  The next attempt begins with `cache.get(...)`; if another owner filled the
  cache, return that hit without reading PostgreSQL.
- [ ] If the lock is obtained, wrap every remaining owner operation in
  `try/finally`; `finally` always awaits `release_fill_lock(..., token=token)`.
- [ ] Immediately after locking, call `cache.get(...)` again. Return a hit;
  otherwise snapshot `generation = await cache.get_generation(...)`, call
  `_read_from_database(query)`, then call `set_if_generation(...)` with the
  configured data TTL and snapshot generation.
- [ ] Return the database lessons only when `set_if_generation()` returns
  `True`. If it returns `False`, leave the `finally` block, then retry the
  entire loop; the invalidator won the race.
- [ ] After the loop is exhausted, raise `ScheduleCacheBusy`.

### Task 5: Wire settings and expose bounded failure correctly

**Files:**
- Modify: `src/schedule_service/app.py`
- Modify: `src/schedule_service/api/dependencies.py`
- Modify: `src/schedule_service/api/lessons.py`

**Consumes:** Task 1 and Task 4.

- [ ] In `create_app()`, save the validated `settings` object in
  `app.state.settings` beside the engine, UoW factory, and cache.
- [ ] In `get_list_lessons_handler()`, pass all four schedule cache settings
  from `request.app.state.settings` to `ListLessonsHandler`.
- [ ] In the `GET /lessons` endpoint, catch `ScheduleCacheBusy` and raise:

```python
HTTPException(
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    detail="Schedule cache is busy",
)
```

  Preserve the exception chain with `from exc`.

### Task 6: Run only static checks before handing back

**Files:** no test files.

- [ ] Run:

```bash
poetry run ruff check .
poetry run ruff format --check .
```

- [ ] Do not alter tests. Report changed files and command output to the agent.

## Test, review, and verification work — agent

### Task 7: Add protocol tests

**Files:**
- Modify: `tests/test_redis_schedule_cache.py`
- Modify: `tests/test_list_lessons.py`
- Modify: `tests/test_lessons.py`

- [ ] Test lock acquisition uses `NX` and `PX`, and failure returns `False`.
- [ ] Test release invokes Lua with the lock key and supplied token.
- [ ] Test generation default and parsing.
- [ ] Test `set_if_generation` invokes its Lua script with both keys and
  returns `True` for result `1` and `False` for `0`.
- [ ] Test invalidation invokes generation increment/delete Lua once per day.
- [ ] Test a cache hit avoids the UoW.
- [ ] Test a lock holder fills exactly once while a waiter receives the later
  cache hit without a database query.
- [ ] Test a rejected generation-guarded write repeats the guarded flow and
  does not return a stale cache population.
- [ ] Test exhausted bounded retries maps `GET /lessons` to the specified 503
  response.

### Task 8: Review and live verification

**Files:** no production changes unless a review finds a defect.

- [ ] Run the full test suite, Ruff checks, formatting check, and
  `docker compose config --quiet`.
- [ ] Rebuild Compose and demonstrate: cache a class-day GET, update the
  lesson, wait for Kafka invalidation, and verify Redis no longer contains the
  old data key before the next GET repopulates it.
- [ ] Inspect the staged diff for user-owned unrelated changes before commit.
- [ ] Commit the finished production and test slice only after all verification
  commands pass.
