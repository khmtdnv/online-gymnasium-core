# Analytics service: current class workload

## Goal

Add an independent analytics service that builds a periodically refreshed
current workload view for classes. It must not participate in scheduling
commands or become a dependency of the schedule API.

The first report answers:

> For a class and day, how many planned lessons and planned minutes are
> currently scheduled?

The analytics view may lag schedule changes by up to one minute. The schedule
service remains the source of truth for the current lesson list.

## Boundaries and ownership

| Component | Owns | Must not do |
|---|---|---|
| Schedule service | Lesson commands, PostgreSQL lesson state, domain validation | Query analytics or depend on ClickHouse for a command |
| Kafka | Transport of published schedule snapshots | Define lesson business rules |
| Analytics service | Kafka consumption, ClickHouse event history and derived workload | Write to the schedule database or call its command API |
| ClickHouse | Analytical copies and views | Be used as the read source for the live schedule API |

Analytics failure is non-blocking: schedule commands continue to commit; the
analytics consumer catches up once Kafka and ClickHouse recover.

## Event contract

The existing cache-invalidation event is insufficient for analytics because it
only says that a schedule changed. Each successful lesson create, reschedule,
or cancel also produces an immutable analytics snapshot through the existing
transactional outbox.

The envelope has:

- event_id: stable identity, derived from the outbox row;
- event_type: an explicit analytics lesson-snapshot event name;
- occurred_at: when the schedule command committed its intended change;
- payload: lesson_id, class_id, starts_at, ends_at, status, and monotonic
  lesson version.

Each event describes the full resulting lesson state, rather than a partial
patch. A cancelled lesson is retained with status = cancelled; it is not
deleted from history.

The current domain rule already confines a lesson interval to one calendar
day. Therefore the first workload computation groups a planned lesson by its
start date and computes its minutes from ends_at minus starts_at.

## Data flow

1. Schedule command commits lesson mutation and outbox rows in one PostgreSQL
   transaction.
2. The existing outbox relay publishes the analytics snapshot to Kafka.
3. The analytics consumer, using its own Kafka consumer group, inserts the
   received snapshot into ClickHouse.
4. ClickHouse retains the append-only snapshots.
5. A refreshable materialized view runs every minute. It selects the latest
   snapshot per lesson, excludes cancelled lessons, groups by class and day,
   and atomically replaces the workload result.
6. A future analytics API or dashboard reads the workload result together with
   its refresh timestamp.

This intentionally tolerates at-least-once Kafka delivery. The raw history
keeps the stable event_id; the latest-state query uses the highest lesson
version. Duplicate delivery may create a duplicate physical row, but it must
not alter the logical current lesson state or workload result.

## ClickHouse model

### lesson_snapshots

Append-only input table.

Columns:

- event_id, occurred_at;
- lesson_id, class_id;
- starts_at, ends_at;
- status, version.

The table is append-only: it preserves the analytical history, including
duplicate Kafka deliveries. The refresh query explicitly derives the latest
snapshot per lesson from its highest version. Identical duplicate events do
not change that logical current state.

### class_daily_workload

Target table owned by the refreshable materialized view.

Columns:

- class_id;
- day;
- planned_lessons_count;
- planned_minutes;
- refreshed_at.

The view atomically replaces this table's contents on each run. It is
therefore appropriate for current state: a reschedule removes the old
day's contribution and adds the new day's contribution during the same
recalculation.

## Failure behaviour

| Failure | Behaviour |
|---|---|
| Schedule transaction fails | No lesson mutation and no analytics outbox event |
| Relay crashes after Kafka publish | Kafka may receive a duplicate after restart; analytics result remains logically correct |
| Analytics consumer crashes before Kafka offset commit | Kafka redelivers; same duplicate-safety rule applies |
| ClickHouse is unavailable | Consumer does not commit the Kafka message and retries later |
| Refresh fails | Last successful workload table remains available; its timestamp exposes staleness |

## Runtime topology

Compose gains:

- clickhouse: persistent analytical database;
- analytics: long-running Kafka consumer with ClickHouse configuration.

analytics waits for Kafka and ClickHouse health. Neither it nor ClickHouse
is a dependency of the schedule API or migrations service.

The first healthcheck is liveness of the analytics process. A later slice can
add readiness that verifies both Kafka and ClickHouse connectivity.

## Verification

Unit tests cover:

- parsing a documented Kafka envelope;
- mapping it to a ClickHouse snapshot insert;
- duplicate and older-version behaviour when selecting current lesson state;
- the workload query's exclusion of cancelled lessons and calculation of
  planned minutes.

Compose smoke test:

1. Create a lesson.
2. Wait for relay, consumer, and one refresh cycle.
3. Query ClickHouse: class-day workload includes its count and minutes.
4. Reschedule the lesson to another day or cancel it.
5. After the next refresh, verify the old/new day workload is corrected.

## Explicit non-goals

- Real-time dashboard accuracy below the one-minute refresh interval.
- Teacher-level workload, school-wide summaries, and charts.
- Backfilling historical data before analytics begins consuming.
- Analytics commands or writes back into schedule.
- An analytics HTTP API in this first slice.

## Verified ClickHouse assumptions

ClickHouse documents refreshable materialized views as periodic full-query
recomputations that atomically replace the target result. Incremental views,
by contrast, process only newly inserted blocks. The selected design avoids
depending on asynchronous table-engine deduplication: the refresh query
chooses the highest lesson version explicitly.

Sources checked 2026-09-18:

- https://clickhouse.com/blog/common-getting-started-issues-with-clickhouse
- https://learn.clickhouse.com/visitor_catalog_class/show/1914307
