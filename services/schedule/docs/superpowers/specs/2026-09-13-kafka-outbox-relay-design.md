# Kafka outbox relay

## Goal

Deliver committed `lesson.created` events from PostgreSQL outbox rows to Kafka
without making the HTTP API dependent on Kafka availability. This slice stops
after publishing to Kafka. Analytics, ClickHouse consumers, and emitting
`lesson.rescheduled` or `lesson.canceled` are explicitly out of scope.

## Decisions

- Run exactly one long-lived `outbox-relay` process in local Compose.
- Publish the currently emitted `lesson.created` events to the single topic
  `schedule.lessons`.
- Use the lesson id as the Kafka message key. This preserves write order for a
  given lesson within its Kafka partition.
- Use `event_id`, the primary key of `outbox_events`, as the idempotency key
  for future consumers.
- Provide at-least-once delivery. A duplicate is acceptable; a confirmed event
  must not be silently discarded.
- Use the asynchronous Python client `aiokafka` and the pinned official Docker
  image `apache/kafka:4.3.1` for local development.

Future `lesson.rescheduled` and `lesson.canceled` events will use this same
topic, envelope, key, and relay. Their handlers must first add corresponding
outbox rows inside their existing lesson transactions.

## Message contract

The relay publishes UTF-8 JSON values with this envelope:

```json
{
  "event_id": 42,
  "event_type": "lesson.created",
  "occurred_at": "2026-09-13T12:00:00+00:00",
  "payload": {
    "lesson_id": 6,
    "class_id": 700,
    "teacher_id": 800,
    "subject_id": 900,
    "starts_at": "2026-09-10T10:00:00+00:00",
    "ends_at": "2026-09-10T11:00:00+00:00",
    "status": "planned",
    "version": 1
  }
}
```

`event_id` is supplied from the outbox row, `event_type` and `payload` from
that row, and `occurred_at` from `created_at`. The Kafka key is the UTF-8
decimal representation of `payload.lesson_id`.

## Components and boundaries

```text
HTTP API --one PostgreSQL transaction--> scheduled_lessons + outbox_events
                                                        |
                                                        v
                   outbox-relay --confirmed publish--> Kafka schedule.lessons
```

- The API continues to create an outbox event only. It does not import or call
  Kafka code.
- `OutboxRepository` gains read-pending and mark-published operations in
  addition to adding an event.
- `OutboxRelay` is application orchestration: it receives an outbox repository
  factory and an event-publisher port.
- `KafkaEventPublisher` is infrastructure: it owns an `AIOKafkaProducer` and
  serializes the documented envelope.
- `workers/outbox_relay.py` is the composition root for the relay process. It
  creates one `AsyncEngine` for its lifetime, creates short-lived sessions for
  repository operations, starts one producer, and closes both on shutdown.

## Delivery algorithm

1. Relay reads at most 100 rows with `published_at IS NULL`, ordered by `id`.
2. For each row, it builds the message envelope and calls
   `send_and_wait(topic, value, key)`.
3. Only after that call succeeds does the relay set `published_at` to the
   current UTC timestamp in a separate short PostgreSQL transaction.
4. With no pending rows it sleeps for one second, then polls again.
5. A Kafka publishing failure is logged; the row remains pending and is retried
   after the sleep interval.

The relay never retains a PostgreSQL transaction or row lock while it waits for
Kafka network I/O.

## Failure semantics

- Failure before Kafka confirms publish: the row stays pending; no known Kafka
  event exists.
- Failure after Kafka confirms publish but before PostgreSQL marks it: the row
  is retried after restart and Kafka may contain a duplicate.
- Future consumers must persist or otherwise remember processed `event_id`
  values before applying non-idempotent effects.
- This initial version intentionally has no lease, retry counter, dead-letter
  topic, or multi-relay coordination. Those are required only before running
  multiple relay processes.

## Configuration and Compose

- Add required `KAFKA_BOOTSTRAP_SERVERS` to `Settings` and `.env.example`.
- Add the `aiokafka` main dependency, pinned in `poetry.lock`.
- Add one `kafka` Compose service using `apache/kafka:4.3.1` and a healthcheck.
- Add an `outbox-relay` Compose service built from the existing Dockerfile.
- `outbox-relay` depends on successful migrations and a healthy Kafka broker.
- Keep PostgreSQL, API, migrations, and RabbitMQ-related configuration unchanged.

## Verification

- Unit test: relay publishes a pending row and marks it published only after a
  successful publisher call.
- Unit test: publisher failure leaves `published_at` unchanged.
- Repository test: pending rows are read in id order and `mark_published`
  updates the selected row only.
- Compose runtime test: create a lesson through the API, observe one record on
  `schedule.lessons`, then confirm its outbox row has a non-null `published_at`.

## Sources

- Apache Kafka 4.3 introduction: topics are retained event streams, partitioned
  for scale, and preserve order for records with the same key within a
  partition. <https://kafka.apache.org/43/getting-started/introduction/>
- Apache Kafka 4.3 Docker guide: official JVM image and pinned `4.3.1` tag.
  <https://kafka.apache.org/43/getting-started/docker/>
- aiokafka 0.14.0: asynchronous producer lifecycle and `send_and_wait` usage;
  supports Python 3.14. <https://pypi.org/project/aiokafka/>
