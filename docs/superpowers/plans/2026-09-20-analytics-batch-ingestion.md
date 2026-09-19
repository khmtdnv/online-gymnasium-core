# Analytics Batch Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Write batches of analytics snapshots to ClickHouse while committing each
Kafka partition only after its fetched records have completed their ClickHouse
or DLQ work.

**Architecture:** The worker changes from per-record async iteration to bounded
`getmany` polling. A repository method maps many immutable `LessonSnapshot`
DTOs to one ClickHouse insert. The worker retains ownership of Kafka polling,
payload classification, DLQ delivery, and per-partition commits.

**Tech Stack:** Python 3.14, aiokafka 0.14, clickhouse-connect 1.8, pytest,
Ruff, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-20-analytics-batch-ingestion-design.md`

## Global Constraints

- Use `consumer.getmany(timeout_ms=1000, max_records=100)`; do not retain
  messages longer than one polling second in an idle local worker.
- Do not add a Unit of Work, a rebalance listener, Kafka partitions, a DLQ
  replay command, an exporter, or exactly-once delivery.
- Preserve the existing DLQ topic and envelope fields exactly.
- Commit the next offset (`last processed offset + 1`) separately for each
  topic-partition only after all operations for the fetched result succeed.
- `ClickHouseSnapshotRepository` keeps synchronous client I/O behind
  `asyncio.to_thread`.
- Keep Ruff target Python 3.14 and the existing 88-character line limit.

## Review Focus

- An empty `getmany` result must issue neither a ClickHouse insert nor a Kafka
  commit; Task 2 pins this with an empty fake poll followed by cancellation.
- An ignored event still advances its partition because it needs no ClickHouse
  row; Task 2 pins its per-partition commit.
- A batch with two valid snapshots must call ClickHouse once with two rows;
  Task 1 pins the row matrix and Task 2 pins the one `add_many` call.
- A ClickHouse failure must produce no source commit; Task 2 pins this branch.
- A malformed record must continue using the existing DLQ path and commit only
  after successful DLQ publication; Task 2 migrates the existing DLQ test to
  the batch polling fixture.

---

## File structure

| File | Responsibility |
| --- | --- |
| `services/analytics/src/analytics_service/infrastructure/clickhouse_snapshot_repository.py` | Map a non-empty `list[LessonSnapshot]` to one ClickHouse row matrix and one insert. |
| `services/analytics/src/analytics_service/workers/worker.py` | Poll Kafka in bounded batches, classify messages, call `add_many`, publish DLQ records, commit per partition. |
| `services/analytics/tests/test_clickhouse_repository.py` | Verify multi-row and empty batch repository behavior. |
| `services/analytics/tests/test_worker.py` | Model `getmany` polling and prove commit boundaries around valid, ignored, malformed and failed batches. |

## Task 1: Bulk snapshot repository

**Files:**
- Modify: `services/analytics/src/analytics_service/infrastructure/clickhouse_snapshot_repository.py`
- Modify: `services/analytics/tests/test_clickhouse_repository.py`

**Interfaces:**
- Consumes: `list[LessonSnapshot]`.
- Produces: `async def add_many(self, snapshots: list[LessonSnapshot]) -> None`.
- Replaces: `async def add(self, snapshot: LessonSnapshot) -> None`.

- [ ] **Step 1: Codex writes two failing repository tests**

Replace the current single-row test with a two-snapshot test whose expected
`client.insert` argument is a literal two-row matrix. Add the empty case:

```python
await repository.add_many([])

client.insert.assert_not_called()
```

The two-row test must call `await repository.add_many([first, second])` and
assert one `client.insert("lesson_snapshots", [first_row, second_row],
column_names=COLUMN_NAMES)`, where `COLUMN_NAMES` is the literal list:

```python
[
    "event_id",
    "occurred_at",
    "lesson_id",
    "class_id",
    "teacher_id",
    "subject_id",
    "starts_at",
    "ends_at",
    "status",
    "version",
]
```

- [ ] **Step 2: Codex verifies RED**

Run:

```bash
poetry run pytest tests/test_clickhouse_repository.py -q
```

Expected: FAIL because `add_many` does not exist yet.

- [ ] **Step 3: Learner implements `add_many`**

Replace `add` with:

```python
async def add_many(self, snapshots: list[LessonSnapshot]) -> None:
    if not snapshots:
        return

    rows = [
        [
            snapshot.event_id,
            snapshot.occurred_at,
            snapshot.lesson_id,
            snapshot.class_id,
            snapshot.teacher_id,
            snapshot.subject_id,
            snapshot.starts_at,
            snapshot.ends_at,
            snapshot.status,
            snapshot.version,
        ]
        for snapshot in snapshots
    ]
    await asyncio.to_thread(
        self._client.insert,
        "lesson_snapshots",
        rows,
        column_names=COLUMN_NAMES,
    )
```

Define `COLUMN_NAMES` once at module scope as the existing ordered list of ten
database columns:

```python
COLUMN_NAMES = [
    "event_id",
    "occurred_at",
    "lesson_id",
    "class_id",
    "teacher_id",
    "subject_id",
    "starts_at",
    "ends_at",
    "status",
    "version",
]
```

Do not move DTOs or add a port for this internal adapter.

- [ ] **Step 4: Learner verifies GREEN**

Run:

```bash
poetry run pytest tests/test_clickhouse_repository.py -q
poetry run ruff check .
poetry run ruff format --check .
```

Expected: repository tests and Ruff pass.

## Task 2: Kafka batch polling and safe commit boundary

**Files:**
- Modify: `services/analytics/src/analytics_service/workers/worker.py`
- Modify: `services/analytics/tests/test_worker.py`

**Interfaces:**
- Consumes: `dict[TopicPartition, list[ConsumerRecord]]` returned by
  `await consumer.getmany(timeout_ms=1000, max_records=100)`.
- Consumes: `ClickHouseSnapshotRepository.add_many(snapshots)` from Task 1.
- Produces: `await consumer.commit({topic_partition: last_offset + 1})` only
  after processing each returned partition list.

- [ ] **Step 1: Codex converts the worker fixture to poll batches**

Replace `FakeConsumer.__aiter__` with an `AsyncMock` `getmany` whose
`side_effect` is a sequence of batch dictionaries followed by
`asyncio.CancelledError`. Make each message fixture include `topic`,
`partition`, `offset`, and `value`. Use a real
`TopicPartition("schedule.lessons", 0)` as the dictionary key.

- [ ] **Step 2: Codex writes failing batch behavior tests**

Add a successful two-record batch test:

```python
topic_partition = TopicPartition("schedule.lessons", 0)
consumer = FakeConsumer(
    [
        {
            topic_partition: [
                first_snapshot_message(offset=10),
                second_snapshot_message(offset=11),
            ]
        }
    ]
)

with pytest.raises(asyncio.CancelledError):
    await worker.run()

repository.add_many.assert_awaited_once()
snapshots = repository.add_many.await_args.args[0]
assert [snapshot.event_id for snapshot in snapshots] == [42, 43]
consumer.commit.assert_awaited_once_with({topic_partition: 12})
```

Add these focused tests as well:

```python
# An empty poll: no repository call and no commit.
consumer = FakeConsumer([{}])

# An ignored schedule.changed at offset 7: no repository call,
# commit {topic_partition: 8}.

# ClickHouse add_many raises RuntimeError("ClickHouse is unavailable"):
# worker re-raises and consumer.commit is not awaited.
```

Migrate the existing malformed-payload test to this fixture. It must assert
one DLQ publish and `consumer.commit({topic_partition: 8})` after the DLQ
send succeeds. Migrate the existing DLQ-publish-failure test too; it must
assert no commit.

- [ ] **Step 3: Codex verifies RED**

Run:

```bash
poetry run pytest tests/test_worker.py -q
```

Expected: FAIL because the worker still uses async iteration and calls `add`,
not `getmany` and `add_many`.

- [ ] **Step 4: Learner implements one fetched-batch loop**

Replace the `async for message in consumer` block with this control flow:

```python
while True:
    fetched = await consumer.getmany(timeout_ms=1000, max_records=100)

    for topic_partition, messages in fetched.items():
        snapshots: list[LessonSnapshot] = []
        malformed_messages = []

        for message in messages:
            try:
                envelope = json.loads(message.value)
                snapshot = parse_lesson_snapshot(envelope)
            except (
                json.JSONDecodeError,
                UnicodeDecodeError,
                TypeError,
                ValueError,
            ) as exc:
                malformed_messages.append((message, exc))
            else:
                if snapshot is not None:
                    snapshots.append(snapshot)

        if snapshots:
            await repository.add_many(snapshots)
        for malformed_message, exc in malformed_messages:
            dlq_envelope = {
                "source_topic": malformed_message.topic,
                "source_partition": malformed_message.partition,
                "source_offset": malformed_message.offset,
                "failed_at": datetime.now(UTC).isoformat(),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "original_value_base64": base64.b64encode(
                    malformed_message.value
                ).decode("ascii"),
            }
            await producer.send_and_wait(
                settings.analytics_dlq_topic,
                json.dumps(
                    dlq_envelope, sort_keys=True, separators=(",", ":")
                ).encode(),
            )

        if messages:
            await consumer.commit({topic_partition: messages[-1].offset + 1})
```

Keep the outer logging-and-reraise block: errors from ClickHouse, DLQ
publication and commit must escape it. The DLQ envelope preserves its seven
existing fields and base64 payload encoding exactly.

- [ ] **Step 5: Learner verifies GREEN**

Run:

```bash
poetry run pytest tests/test_worker.py -q
poetry run pytest -q
poetry run ruff check .
poetry run ruff format --check .
```

Expected: all analytics tests and Ruff pass. The known FastAPI/Starlette
test-client deprecation warnings may remain, but no test fails.

## Task 3: Live batch proof and commit

**Files:**
- Modify: no production files beyond Tasks 1–2.

**Interfaces:**
- Consumes: the completed worker and Kafka group `schedule-analytics`.
- Produces: runtime evidence that valid batch ingestion commits only after the
  worker runs, while the previously verified DLQ behavior remains intact.

- [ ] **Step 1: Codex rebuilds and starts the worker**

Run from repository root:

```bash
docker compose up --build -d analytics-worker
docker compose ps analytics-worker
```

- [ ] **Step 2: Codex publishes two distinct valid snapshot envelopes**

Use `kafka-console-producer.sh` inside the Kafka container to publish two
newline-delimited `lesson.snapshot` JSON envelopes with distinct `event_id`,
`lesson_id`, `class_id`, `starts_at`, `ends_at`, and `version` values to
`schedule.lessons`.

- [ ] **Step 3: Codex proves storage and source progress**

Run:

```bash
docker compose exec clickhouse clickhouse-client --query \
  "SELECT event_id, lesson_id, version FROM lesson_snapshots ORDER BY event_id DESC LIMIT 2"
docker compose exec kafka /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 --describe --group schedule-analytics
```

Expected: both new snapshots exist; worker is `Up`; the group has `LAG 0`.

- [ ] **Step 4: Codex validates final state and commits**

Run:

```bash
poetry -C services/analytics run pytest -q
poetry -C services/analytics run ruff check .
poetry -C services/analytics run ruff format --check .
docker compose config --quiet
git diff --check
git status --short
```

Then create one commit containing only batch-ingestion code and tests:

```bash
git add services/analytics/src/analytics_service/infrastructure/clickhouse_snapshot_repository.py \
  services/analytics/src/analytics_service/workers/worker.py \
  services/analytics/tests/test_clickhouse_repository.py \
  services/analytics/tests/test_worker.py
git commit -m "feat: batch analytics snapshot ingestion"
```

## Plan self-review

- Spec coverage: Tasks 1–2 implement bounded polling, one bulk ClickHouse
  insert, retained DLQ handling, per-partition next-offset commits and
  at-least-once failure behavior. Task 3 verifies the running system.
- Placeholder scan: no deferred behavior or unspecified error handling.
- Type consistency: Task 1 defines `add_many(list[LessonSnapshot])`; Task 2
  consumes exactly that signature. Task 2 commits `{TopicPartition: int}`.
- Review focus: every listed boundary is assigned to Task 1 or Task 2 tests.
