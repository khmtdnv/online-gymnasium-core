# Analytics batch ingestion design

## Purpose

Fulfil the analytics-service legend item “batch data loading”: replace the
current one-ClickHouse-insert-per-Kafka-record flow with bounded batches while
preserving at-least-once processing and the existing DLQ policy.

## Scope and boundaries

The analytics worker remains the only Kafka consumer in scope. It consumes
`schedule.lessons`, writes valid `lesson.snapshot` events to ClickHouse, and
sends malformed input to `analytics.lesson-snapshots.dlq`.

This slice does not add Kafka partitions, a rebalance listener, an external
Kafka exporter, a DLQ replay tool, or exactly-once delivery. Local Compose has
one `schedule.lessons` partition and one worker instance.

## Batch policy

Each call to `consumer.getmany(timeout_ms=1000, max_records=100)` supplies a
bounded batch:

- no more than 100 records are collected before processing;
- an idle worker wakes after one second so a small batch is not retained
  indefinitely;
- valid snapshots from the returned records are sent to ClickHouse in one
  repository call and one client `insert` call.

`100` is deliberately small for the local teaching environment. Production
batch size is workload-specific and must be measured rather than copied.

## Processing and commits

For every returned topic-partition list, the worker classifies each record:

1. valid `lesson.snapshot` events are accumulated as snapshots;
2. deliberately ignored event types require no ClickHouse row;
3. malformed JSON or an invalid snapshot payload is serialized to the existing
   DLQ envelope.

The worker first writes all accumulated valid snapshots with `add_many`, then
publishes each DLQ envelope. Only when all of those operations succeed does it
commit that partition at `last_processed_offset + 1`.

If ClickHouse insertion, DLQ publishing, or Kafka commit fails, the worker
raises. No new source offset is committed for that fetched batch. Kafka can
then redeliver records after restart. Duplicate snapshots remain compatible
with the existing version-based analytics projection; this is at-least-once,
not exactly-once, delivery.

## Code shape

- `ClickHouseSnapshotRepository.add_many(snapshots: list[LessonSnapshot])`
  owns conversion of all snapshot DTOs into one ClickHouse row matrix and calls
  synchronous `client.insert` within `asyncio.to_thread`.
- The worker owns polling, classification, DLQ publishing and per-partition
  offset commits. It must not introduce a Unit of Work because ClickHouse and
  Kafka do not share a transaction.
- The current single-snapshot `add` method is replaced by `add_many`; an empty
  list must not issue an insert.

## Tests and runtime proof

Tests cover one repository bulk insert, no insert for an empty batch, a worker
commit at offset plus one after successful processing, and the no-commit path
when ClickHouse insertion fails. Existing DLQ tests must continue to pass.

Runtime proof publishes several valid snapshot records, then checks one
ClickHouse insert batch through logs/test double evidence and verifies the
Kafka group has no lag only after the batch is persisted.

## Sources

- aiokafka consumer documentation: `getmany` returns records grouped by
  topic-partition; manual commits use the next offset:
  https://aiokafka.readthedocs.io/en/latest/consumer.html
- ClickHouse guidance on batching inserts:
  https://clickhouse.com/blog/common-getting-started-issues-with-clickhouse
