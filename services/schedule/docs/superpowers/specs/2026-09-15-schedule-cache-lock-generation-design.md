# Schedule cache lock and generation gate design

**Date:** 2026-09-15  
**Status:** Approved

## Goal

Harden the class-day schedule cache against two independent concurrent-read
failures while preserving the existing cache-aside and Kafka invalidation
architecture:

1. avoid a cache stampede when many readers see the same cache miss;
2. prevent an in-flight reader from repopulating a key with data that an
   invalidation has already superseded.

This design intentionally uses one Redis instance. It is a token-based Redis
lock, not the multi-node Redlock algorithm.

## Key layout

For one `class_id` and `day`, Redis contains:

```text
schedule:class:{class_id}:date:{YYYY-MM-DD}       cached schedule JSON
schedule:class:{class_id}:date:{YYYY-MM-DD}:gen   invalidation generation
schedule:class:{class_id}:date:{YYYY-MM-DD}:lock  short-lived fill lock
```

The data key keeps the existing cache TTL. The generation is an integer and an
absent key is treated as generation `0`. A lock value is a cryptographically
random ownership token and is created with `SET key token NX PX lock_ttl_ms`.

## Read protocol

`ListLessonsHandler` owns orchestration; the cache adapter owns Redis commands
and Lua scripts.

1. Read the data key. A hit returns immediately.
2. On a miss, try to acquire the fill lock.
3. A non-owner waits with a bounded short retry loop and checks the data key
   after every delay. It never bypasses the lock with a direct database read.
4. The owner checks the data key again after acquiring the lock. This covers
   the interval before it acquired ownership.
5. The owner snapshots generation `G`, reads the database through a new UoW,
   and conditionally writes the serialized result.
6. A Lua script writes the data key with its TTL only when the current
   generation is still `G`. It otherwise rejects the write.
7. In all owner outcomes, a second Lua script deletes the lock only when the
   key still holds this owner's token.
8. A rejected conditional write retries the whole read flow, so its next
   database read observes the state after the invalidation.

If a database read outlives the lock TTL, another reader may become an owner.
Token comparison prevents the original reader from deleting the new owner's
lock. Generation comparison still protects cache correctness; only work
coalescing is weakened for that slow request.

## Invalidation protocol

For each affected class-day key, `RedisScheduleCache.invalidate()` runs a Lua
script that increments the generation and deletes the data key. The operation
is idempotent with respect to the final cache state: repeated invalidations
leave no cached value and advance the generation again.

Kafka delivery remains at-least-once. The existing cache invalidator commits an
offset only after all Redis invalidations complete.

## Consistency boundary

The design prevents this completed race:

```text
Reader:  miss -> generation G -> reads old DB data
Writer:                             commits -> Kafka invalidation -> G + 1, DEL
Reader:                                                              conditional SET(G) rejected
```

It does not make PostgreSQL and Redis synchronously consistent. Before the
outbox relay publishes and the Kafka consumer handles an event, a recently
committed write can briefly coexist with an old cache entry. This is the
intentional eventual-consistency boundary of the existing outbox/Kafka design.

## Interfaces and configuration

`ScheduleCache` gains operations for acquiring/releasing a fill lock, reading
the generation, and conditionally setting data for a generation. Redis-specific
commands and Lua stay in `RedisScheduleCache`; neither domain nor application
code imports Redis types.

API settings add bounded cache-fill parameters with defaults:

- data TTL: 60 seconds;
- lock TTL: 5 seconds;
- retry delay: 50 milliseconds;
- retry limit: 20 attempts.

Exhausting retries fails explicitly rather than silently sending every waiter
to PostgreSQL. This makes overload observable and keeps the anti-stampede
guarantee.

## Tests

Tests cover:

1. ordinary hit and miss behavior remains unchanged;
2. only the token owner can release a lock;
3. invalidation increments generation and removes data;
4. a write with an obsolete generation is rejected;
5. concurrent misses result in one database fetch once the owner publishes;
6. a failed conditional write causes a new read rather than a stale cache set;
7. retries are bounded and failure is visible.

## Non-goals

- multi-Redis Redlock quorum;
- cross-region cache coordination;
- strict synchronous cache consistency with PostgreSQL;
- request coalescing across different class-day keys.
