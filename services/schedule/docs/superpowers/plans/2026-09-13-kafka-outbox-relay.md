# Kafka Outbox Relay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish committed `lesson.created` outbox events from the schedule PostgreSQL database to Kafka topic `schedule.lessons` using one long-lived relay process.

**Architecture:** The API keeps its existing PostgreSQL transaction and records an outbox row; it never calls Kafka. A separate relay reads pending rows in short database sessions, asks an infrastructure Kafka publisher to confirm delivery, then marks the row published in another short session. The known gap between broker acknowledgement and the PostgreSQL update yields at-least-once delivery, so future consumers deduplicate with `event_id`.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy asyncio, PostgreSQL 18, Docker Compose, Apache Kafka `4.3.1`, aiokafka `0.14.x`, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-13-kafka-outbox-relay-design.md`

## Global Constraints

- Scope is only `lesson.created`; `lesson.rescheduled`, `lesson.canceled`, analytics, ClickHouse, multi-relay coordination, leases, retry counters, and dead-letter topics are not part of this plan.
- Topic name is exactly `schedule.lessons`; Kafka key is UTF-8 `lesson_id`; JSON values use the documented `event_id`, `event_type`, `occurred_at`, and `payload` envelope.
- Run exactly one relay. It polls at most 100 pending rows in ascending `id` order and sleeps one second after an empty poll or any failure.
- Mark `published_at` only after `AIOKafkaProducer.send_and_wait()` succeeds. Never hold a database transaction while waiting for Kafka.
- The learner writes production code and Compose configuration. Codex writes tests, runs verification, reviews the learner’s implementation, and makes the scoped commits after approval.

---

## File structure

| File | Responsibility |
| --- | --- |
| `src/schedule_service/application/ports/outbox_repository.py` | Defines the pending-outbox value object and repository read/write contract. |
| `src/schedule_service/application/ports/event_publisher.py` | Defines the boundary used by the relay to publish one pending event. |
| `src/schedule_service/application/outbox_relay.py` | Orchestrates read → publish → mark-published, independent of Kafka client code. |
| `src/schedule_service/infrastructure/outbox_repository.py` | Maps PostgreSQL rows to pending events and updates `published_at`. |
| `src/schedule_service/infrastructure/kafka_event_publisher.py` | Serializes the Kafka envelope and calls `AIOKafkaProducer.send_and_wait`. |
| `src/schedule_service/workers/outbox_relay.py` | Composition root and lifecycle for the relay process. |
| `src/schedule_service/workers/config.py` | Defines worker-only `RelaySettings`, including Kafka bootstrap servers. |
| `compose.yaml` | Adds one Kafka broker and one `outbox-relay` service. |
| `pyproject.toml`, `poetry.lock` | Adds the locked `aiokafka` dependency. |
| `tests/test_outbox_repository.py` | Verifies pending-row mapping and publication marking. |
| `tests/test_outbox_relay.py` | Verifies publish order and failure semantics without Kafka. |
| `tests/test_kafka_event_publisher.py` | Verifies Kafka key and JSON envelope against a mocked producer. |
| `tests/test_relay_config.py` | Verifies that worker-only settings receive the Kafka endpoint. |

### Task 1: Add the Kafka client dependency and local Compose broker

**Files:**
- Modify: `pyproject.toml`
- Modify: `poetry.lock`
- Modify: `compose.yaml`

**Interfaces:**
- Compose makes the host broker reachable at `localhost:9092` and containers at `kafka:19092`.
- The official broker image is `apache/kafka:4.3.1`.

- [x] **Step 1 — Learner: add the dependency**

  Add `aiokafka (>=0.14.0,<0.15.0)` as a main dependency with:

  ```bash
  poetry add aiokafka@^0.14.0
  ```

- [x] **Step 2 — Learner: add the Kafka Compose service**

  Add this service before `migrations` in `compose.yaml`:

  ```yaml
  kafka:
    image: apache/kafka:4.3.1
    hostname: kafka
    ports:
      - "9092:9092"
    environment:
      KAFKA_NODE_ID: 1
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: "CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT,PLAINTEXT_HOST:PLAINTEXT"
      KAFKA_ADVERTISED_LISTENERS: "PLAINTEXT_HOST://localhost:9092,PLAINTEXT://kafka:19092"
      KAFKA_PROCESS_ROLES: "broker,controller"
      KAFKA_CONTROLLER_QUORUM_VOTERS: "1@kafka:29093"
      KAFKA_LISTENERS: "CONTROLLER://:29093,PLAINTEXT_HOST://:9092,PLAINTEXT://:19092"
      KAFKA_INTER_BROKER_LISTENER_NAME: "PLAINTEXT"
      KAFKA_CONTROLLER_LISTENER_NAMES: "CONTROLLER"
      CLUSTER_ID: "4L6g3nShT-eMCtK--X86sw"
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS: 0
      KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: 1
      KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 1
      KAFKA_SHARE_COORDINATOR_STATE_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_SHARE_COORDINATOR_STATE_TOPIC_MIN_ISR: 1
      KAFKA_LOG_DIRS: "/tmp/kraft-combined-logs"
      KAFKA_AUTO_CREATE_TOPICS_ENABLE: "true"
    healthcheck:
      test: ["CMD-SHELL", "/opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list"]
      interval: 5s
      timeout: 3s
      retries: 10
      start_period: 10s
  ```

  Do not add Kafka configuration to the HTTP application's `Settings`,
  `.env.example`, `api`, or `migrations`. The future relay receives it through
  its own `RelaySettings` and Compose service.

- [x] **Step 3 — Codex: verify the bounded infrastructure change**

  Run:

  ```bash
  poetry run pytest -q
  poetry run ruff check .
  poetry run ruff format --check .
  docker compose config --quiet
  docker compose up -d kafka
  docker compose ps kafka
  ```

  Expected: tests and Ruff pass; Compose validates; Kafka reaches `healthy`.

- [x] **Step 4 — Learner: commit the complete task**

  ```bash
  git add pyproject.toml poetry.lock compose.yaml
  git commit -m "chore: add local Kafka broker"
  ```

### Task 2: Extend the outbox repository with pending-event operations

**Files:**
- Modify: `src/schedule_service/application/ports/outbox_repository.py`
- Modify: `src/schedule_service/infrastructure/outbox_repository.py`
- Modify: `tests/test_outbox_repository.py`

**Interfaces:**
- Produces:

  ```python
  @dataclass(frozen=True, slots=True)
  class PendingOutboxEvent:
      id: int
      event_type: str
      payload: dict[str, object]
      created_at: datetime


  class OutboxRepository(Protocol):
      async def add(self, event: LessonCreated) -> None: ...
      async def get_pending(self, *, limit: int) -> list[PendingOutboxEvent]: ...
      async def mark_published(self, *, event_id: int) -> None: ...
  ```

- Consumes: the existing `outbox_events` table; no schema migration is needed.

- [ ] **Step 1 — Codex: write repository tests**

  Add a test which configures `session.scalars.return_value.all.return_value`
  with two `OutboxEventRow` objects (`id=7`, then `id=8`) and asserts:

  ```python
  events = await repository.get_pending(limit=100)

  assert [event.id for event in events] == [7, 8]
  assert events[0].event_type == "lesson.created"
  assert events[0].payload["lesson_id"] == 501
  session.scalars.assert_awaited_once()
  ```

  Add a second test for `mark_published(event_id=7)` that captures the Core
  `UPDATE` passed to `session.execute`, compiles it with the PostgreSQL dialect,
  and asserts that it targets `outbox_events`, filters by `id = 7` and
  `published_at IS NULL`, and assigns `published_at` through `func.now()`.

- [ ] **Step 2 — Codex: run the repository tests and establish RED**

  Run: `poetry run pytest tests/test_outbox_repository.py -q`

  Expected: failure because `get_pending` and `mark_published` do not exist.

- [ ] **Step 3 — Learner: implement the value object and database methods**

  Keep `add()` session-local and synchronous at `session.add(row)`, but rename
  its stored payload key from `"id"` to `"lesson_id"`.

  Implement `get_pending` with a SQLAlchemy `select(OutboxEventRow)`:

  ```python
  statement = (
      select(OutboxEventRow)
      .where(OutboxEventRow.published_at.is_(None))
      .order_by(OutboxEventRow.id)
      .limit(limit)
  )
  rows = (await self._session.scalars(statement)).all()
  ```

  Map each row to `PendingOutboxEvent`. For the local rows created by the
  previous version, normalize the old payload key during read:

  ```python
  payload = dict(row.payload)
  if "lesson_id" not in payload and "id" in payload:
      payload["lesson_id"] = payload.pop("id")
  ```

  Implement the marking statement exactly as:

  ```python
  statement = (
      update(OutboxEventRow)
      .where(
          OutboxEventRow.id == event_id,
          OutboxEventRow.published_at.is_(None),
      )
      .values(published_at=func.now())
  )
  await self._session.execute(statement)
  ```

- [ ] **Step 4 — Codex: verify GREEN and regression safety**

  Run:

  ```bash
  poetry run pytest tests/test_outbox_repository.py tests/test_create_lesson.py tests/test_uow.py -q
  poetry run ruff check .
  poetry run ruff format --check .
  ```

  Expected: all pass. The pre-existing test must now expect
  `payload["lesson_id"]`, not `payload["id"]`.

- [ ] **Step 5 — Codex: commit the complete task**

  ```bash
  git add src/schedule_service/application/ports/outbox_repository.py \
    src/schedule_service/infrastructure/outbox_repository.py \
    tests/test_outbox_repository.py
  git commit -m "feat: add pending outbox repository operations"
  ```

### Task 3: Implement relay orchestration independently of Kafka

**Files:**
- Create: `src/schedule_service/application/ports/event_publisher.py`
- Create: `src/schedule_service/application/outbox_relay.py`
- Create: `tests/test_outbox_relay.py`

**Interfaces:**
- Consumes `PendingOutboxEvent` and the existing `UnitOfWorkFactory`.
- Produces:

  ```python
  class EventPublisher(Protocol):
      async def publish(self, event: PendingOutboxEvent) -> None: ...


  class OutboxRelay:
      def __init__(
          self,
          uow_factory: UnitOfWorkFactory,
          publisher: EventPublisher,
          batch_size: int = 100,
      ) -> None: ...

      async def run_once(self) -> int: ...
  ```

- [ ] **Step 1 — Codex: write relay tests with fakes**

  Create a fake UoW factory returning fresh fake UoWs that share one fake
  outbox repository. Let `get_pending()` return events `7` and `8`; let the
  fake publisher append each event id to `published`.

  ```python
  delivered = await relay.run_once()

  assert delivered == 2
  assert publisher.published == [7, 8]
  assert outbox.marked_published == [7, 8]
  ```

  Add a failure test where `publisher.publish()` raises `ConnectionError` for
  event `7`. Assert the exception leaves `run_once`, no event is marked
  published, and event `8` is not attempted:

  ```python
  with pytest.raises(ConnectionError):
      await relay.run_once()

  assert outbox.marked_published == []
  assert publisher.published == [7]
  ```

- [ ] **Step 2 — Codex: run the focused tests and establish RED**

  Run: `poetry run pytest tests/test_outbox_relay.py -q`

  Expected: collection error because `application.outbox_relay` is absent.

- [ ] **Step 3 — Learner: implement the port and `run_once`**

  `EventPublisher` contains only `publish()`. `OutboxRelay.run_once()` must:

  1. open a UoW, call `uow.outbox.get_pending(limit=self._batch_size)`, and
     exit that UoW before any Kafka call;
  2. for each returned event, await `self._publisher.publish(event)`;
  3. only on success, open a new UoW and await
     `uow.outbox.mark_published(event_id=event.id)`;
  4. return the number of successfully published events.

  Do not catch the publisher exception here: the process loop in Task 4 owns
  logging and the one-second retry delay.

- [ ] **Step 4 — Codex: verify GREEN**

  Run:

  ```bash
  poetry run pytest tests/test_outbox_relay.py tests/test_uow.py -q
  poetry run ruff check .
  poetry run ruff format --check .
  ```

  Expected: all pass. The test must prove that no UoW/transaction survives the
  awaited publisher call.

- [ ] **Step 5 — Codex: commit the complete task**

  ```bash
  git add src/schedule_service/application/ports/event_publisher.py \
    src/schedule_service/application/outbox_relay.py tests/test_outbox_relay.py
  git commit -m "feat: add outbox relay application service"
  ```

### Task 4: Implement the aiokafka publisher and worker lifecycle

**Files:**
- Create: `src/schedule_service/infrastructure/kafka_event_publisher.py`
- Create: `src/schedule_service/workers/__init__.py`
- Create: `src/schedule_service/workers/config.py`
- Create: `src/schedule_service/workers/outbox_relay.py`
- Create: `tests/test_kafka_event_publisher.py`
- Create: `tests/test_relay_config.py`

**Interfaces:**
- Consumes `EventPublisher`, `PendingOutboxEvent`, `RelaySettings`,
  `create_engine()`, `create_session_factory()`, and `SqlAlchemyUnitOfWork`.
- Produces:

  ```python
  class KafkaEventPublisher:
      def __init__(self, producer: AIOKafkaProducer, topic: str) -> None: ...
      async def publish(self, event: PendingOutboxEvent) -> None: ...


  async def run() -> None: ...
  ```

- [ ] **Step 1 — Codex: write the publisher contract test**

  Use `AsyncMock(spec=AIOKafkaProducer)`. Publish a `PendingOutboxEvent` with
  id `42`, event type `lesson.created`, known `created_at`, and `lesson_id`
  `501` in its payload. Assert exactly one await:

  ```python
  producer.send_and_wait.assert_awaited_once_with(
      "schedule.lessons",
      expected_json_bytes,
      key=b"501",
  )
  ```

  Decode `expected_json_bytes` with `json.loads()` and assert this envelope:

  ```python
  {
      "event_id": 42,
      "event_type": "lesson.created",
      "occurred_at": "2026-09-13T12:00:00+00:00",
      "payload": {"lesson_id": 501},
  }
  ```

- [ ] **Step 2 — Codex: run the test and establish RED**

  Run: `poetry run pytest tests/test_kafka_event_publisher.py -q`

  Expected: collection error because the infrastructure publisher is absent.

- [ ] **Step 3 — Learner: implement Kafka serialization**

  In `KafkaEventPublisher.publish()`, create the envelope from the pending
  event, encode it as deterministic compact UTF-8 JSON, and await:

  ```python
  await self._producer.send_and_wait(
      self._topic,
      json.dumps(envelope, separators=(",", ":")).encode(),
      key=str(event.payload["lesson_id"]).encode(),
  )
  ```

  `event.payload` was normalized by Task 2, so the key exists for both newly
  created and old local outbox rows.

- [ ] **Step 4 — Learner: implement the worker composition root**

  Codex first adds a focused RED test for `RelaySettings`, setting
  `KAFKA_BOOTSTRAP_SERVERS` through `monkeypatch` and asserting it is loaded.

  Define worker-only settings in `workers/config.py`:

  ```python
  class RelaySettings(BaseSettings):
      model_config = SettingsConfigDict(env_file=".env")
      database_url: str
      kafka_bootstrap_servers: str
  ```

  `run()` creates `RelaySettings()`, one engine and one session factory, then uses:

  ```python
  producer = AIOKafkaProducer(
      bootstrap_servers=settings.kafka_bootstrap_servers,
      acks="all",
  )
  publisher = KafkaEventPublisher(producer, topic="schedule.lessons")
  relay = OutboxRelay(
      uow_factory=lambda: SqlAlchemyUnitOfWork(session_factory),
      publisher=publisher,
  )
  ```

  Await `producer.start()` before the loop. In `finally`, await
  `producer.stop()` and `engine.dispose()`. The loop must initialize
  `published = 0`, catch and log `Exception` around `relay.run_once()`, then
  await `asyncio.sleep(0 if published else 1)`. Run it through
  `asyncio.run(run())` under `if __name__ == "__main__":`.

- [ ] **Step 5 — Codex: verify unit GREEN**

  Run:

  ```bash
  poetry run pytest tests/test_kafka_event_publisher.py tests/test_outbox_relay.py -q
  poetry run ruff check .
  poetry run ruff format --check .
  ```

  Expected: all pass; no test connects to a real broker.

- [ ] **Step 6 — Codex: commit the complete task**

  ```bash
  git add src/schedule_service/infrastructure/kafka_event_publisher.py \
    src/schedule_service/workers tests/test_kafka_event_publisher.py
  git commit -m "feat: publish outbox events to Kafka"
  ```

### Task 5: Wire the relay into Compose and prove the running system

**Files:**
- Modify: `compose.yaml`

**Interfaces:**
- Consumes the worker module from Task 4 and Kafka service from Task 1.
- Produces a healthy Kafka container and an `outbox-relay` service that runs
  until stopped.

- [ ] **Step 1 — Learner: add the `outbox-relay` service**

  Add this service to `compose.yaml`:

  ```yaml
  outbox-relay:
    build:
      context: .
    env_file:
      - .env
      - .postgres.env
    command:
      - /bin/sh
      - -c
      - >
        DATABASE_URL="postgresql+asyncpg://$${POSTGRES_USER}:$${POSTGRES_PASSWORD}@postgres:5432/$${POSTGRES_DB}"
        KAFKA_BOOTSTRAP_SERVERS="kafka:19092"
        exec poetry run python -m schedule_service.workers.outbox_relay
    depends_on:
      migrations:
        condition: service_completed_successfully
      kafka:
        condition: service_healthy
  ```

- [ ] **Step 2 — Codex: validate the Compose contract**

  Run:

  ```bash
  docker compose config --quiet
  docker compose up --build -d
  docker compose ps -a
  ```

  Expected: `postgres`, `kafka`, and `api` become healthy; `migrations` exits
  with status 0; `outbox-relay` remains running.

- [ ] **Step 3 — Codex: execute the end-to-end delivery check**

  Post a unique lesson such as class `9901`, teacher `9902`, subject `9903`:

  ```bash
  curl -i -X POST http://127.0.0.1:8000/lessons \
    -H 'content-type: application/json' \
    -d '{"class_id":9901,"teacher_id":9902,"subject_id":9903,"starts_at":"2026-10-01T10:00:00Z","ends_at":"2026-10-01T11:00:00Z"}'
  ```

  Consume the topic from the beginning and inspect the event with that unique
  class id:

  ```bash
  docker compose exec kafka kafka-console-consumer.sh \
    --bootstrap-server kafka:19092 \
    --topic schedule.lessons \
    --from-beginning \
    --timeout-ms 10000 | grep '"class_id":9901'
  ```

  Then query the matching outbox row:

  ```bash
  docker compose exec postgres psql -U schedule -d schedule -c \
    "SELECT id, event_type, published_at FROM outbox_events WHERE payload->>'class_id' = '9901';"
  ```

  Expected: one Kafka JSON message carries `event_type: lesson.created`, its
  `event_id` equals the database row id, and the row has non-null
  `published_at`.

- [ ] **Step 4 — Codex: exercise retry semantics**

  Stop Kafka, create another unique lesson, and verify its `published_at` is
  still null. Start Kafka again and poll the same row until `published_at` is
  non-null. The API must return `201 Created` while Kafka is stopped.

  ```bash
  docker compose stop kafka
  docker compose start kafka
  ```

  Expected: the relay logs a publish failure while Kafka is down, remains
  running, and eventually delivers after recovery without restarting API or
  relay.

- [ ] **Step 5 — Codex: full verification and commit**

  Run:

  ```bash
  poetry run pytest -q
  poetry run ruff check .
  poetry run ruff format --check .
  poetry run alembic current
  docker compose config --quiet
  git diff --check
  ```

  Commit only the remaining intended relay/configuration files:

  ```bash
  git add compose.yaml
  git commit -m "feat: run Kafka outbox relay in Compose"
  ```

  Expected: all checks pass and the working tree is clean apart from any files
  the learner explicitly kept outside this scope.
