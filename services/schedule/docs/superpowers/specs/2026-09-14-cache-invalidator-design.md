# Cache invalidator design

## Goal

Keep cached class schedules fresh after a lesson is created, rescheduled, or
cancelled, without making the HTTP API publish directly to Kafka.

## Event contract

Writers add a `schedule.changed` outbox event in the same database transaction
as the lesson mutation. Its payload is:

```json
{
  "class_id": 10,
  "affected_dates": ["2026-09-10", "2026-09-11"]
}
```

The domain forbids an interval crossing midnight, so `affected_dates` has one
item for creation and cancellation. For a reschedule it contains the distinct
old and new dates, since a lesson can move from one calendar day to another.

The payload is deliberately cache-oriented: the consumer does not duplicate
lesson interval logic.

## Components and flow

1. Create, update, and cancel application handlers build the event payload and
   add it through the existing outbox repository.
2. The existing outbox relay publishes `schedule.changed` to `schedule.lessons`
   in the existing JSON envelope.
3. A long-running `cache-invalidator` worker consumes that topic in its own
   Kafka consumer group.
4. For each affected day, it deletes
   `schedule:class:{class_id}:date:{YYYY-MM-DD}` from Redis.
5. It commits the Kafka offset only after Redis deletion succeeds.

Kafka's at-least-once delivery is safe here: Redis `DEL` is idempotent, so an
event can be handled repeatedly without corrupting cache state.

## Configuration and deployment

`InvalidatorSettings` is separate from API and relay settings. It reads only
`KAFKA_BOOTSTRAP_SERVERS` and `REDIS_URL`. Compose creates a
`cache-invalidator` service after Kafka and Redis are healthy. The API and
migrations remain free of Kafka configuration.

## Failure policy

- Redis failure: log and leave the Kafka offset uncommitted so Kafka redelivers
  the event.
- Missing Redis key: successful invalidation.
- Malformed event payload: log an error and do not commit the offset, exposing
  the contract break rather than silently leaving stale cache data.

## Verification

- Unit-test that creation and rescheduling reject an interval crossing
  midnight.
- Unit-test the three writer handlers adding correct events.
- Unit-test the worker deletes exact Redis keys and commits only after success.
- Run all tests, Ruff, Compose validation, and an end-to-end Compose check:
  populate a cache entry, mutate a lesson, observe key deletion, then confirm a
  subsequent read rebuilds the entry.
