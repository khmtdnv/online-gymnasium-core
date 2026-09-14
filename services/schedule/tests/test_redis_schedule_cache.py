import json
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import pytest

from schedule_service.domain.lesson import Lesson
from schedule_service.infrastructure.redis_schedule_cache import (
    _RELEASE_LOCK_SCRIPT,
    _SET_IF_GENERATION_SCRIPT,
    RedisScheduleCache,
)


@pytest.mark.anyio
async def test_cache_restores_lessons_from_json_for_class_and_day() -> None:
    client = AsyncMock()
    client.get.return_value = json.dumps(
        [
            {
                "id": 501,
                "class_id": 10,
                "teacher_id": 100,
                "subject_id": 1000,
                "starts_at": "2026-09-10T10:00:00+00:00",
                "ends_at": "2026-09-10T11:00:00+00:00",
                "status": "planned",
                "version": 1,
            }
        ]
    )
    cache = RedisScheduleCache(client)

    lessons = await cache.get(class_id=10, day=date(2026, 9, 10))

    assert lessons == [
        Lesson(
            id=501,
            class_id=10,
            teacher_id=100,
            subject_id=1000,
            starts_at=datetime(2026, 9, 10, 10, tzinfo=UTC),
            ends_at=datetime(2026, 9, 10, 11, tzinfo=UTC),
            status="planned",
            version=1,
        )
    ]
    client.get.assert_awaited_once_with("schedule:class:10:date:2026-09-10")


@pytest.mark.anyio
async def test_cache_stores_lessons_only_when_generation_matches() -> None:
    client = AsyncMock()
    cache = RedisScheduleCache(client)
    lessons = [
        Lesson(
            id=501,
            class_id=10,
            teacher_id=100,
            subject_id=1000,
            starts_at=datetime(2026, 9, 10, 10, tzinfo=UTC),
            ends_at=datetime(2026, 9, 10, 11, tzinfo=UTC),
            status="planned",
            version=1,
        )
    ]

    client.eval.return_value = 1

    stored = await cache.set_if_generation(
        class_id=10,
        day=date(2026, 9, 10),
        lessons=lessons,
        ttl_seconds=60,
        expected_generation=4,
    )

    assert stored is True
    script, key_count, key, generation_key, generation, serialized, ttl = (
        client.eval.await_args.args
    )
    assert script == _SET_IF_GENERATION_SCRIPT
    assert key_count == 2
    assert key == "schedule:class:10:date:2026-09-10"
    assert generation_key == "schedule:class:10:date:2026-09-10:gen"
    assert generation == "4"
    assert ttl == "60"
    assert json.loads(serialized) == [
        {
            "id": 501,
            "class_id": 10,
            "teacher_id": 100,
            "subject_id": 1000,
            "starts_at": "2026-09-10T10:00:00+00:00",
            "ends_at": "2026-09-10T11:00:00+00:00",
            "status": "planned",
            "version": 1,
        }
    ]


@pytest.mark.anyio
async def test_cache_returns_false_when_generation_changed_during_database_read() -> (
    None
):
    client = AsyncMock()
    client.eval.return_value = 0
    cache = RedisScheduleCache(client)

    stored = await cache.set_if_generation(
        class_id=10,
        day=date(2026, 9, 10),
        lessons=[],
        ttl_seconds=60,
        expected_generation=4,
    )

    assert stored is False


@pytest.mark.anyio
async def test_cache_reads_zero_for_missing_generation() -> None:
    client = AsyncMock()
    client.get.return_value = None
    cache = RedisScheduleCache(client)

    generation = await cache.get_generation(class_id=10, day=date(2026, 9, 10))

    assert generation == 0
    client.get.assert_awaited_once_with("schedule:class:10:date:2026-09-10:gen")


@pytest.mark.anyio
async def test_cache_acquires_fill_lock_with_token_and_ttl() -> None:
    client = AsyncMock()
    client.set.return_value = True
    cache = RedisScheduleCache(client)

    acquired = await cache.try_acquire_fill_lock(
        class_id=10,
        day=date(2026, 9, 10),
        token="owner-token",
        ttl_ms=5000,
    )

    assert acquired is True
    client.set.assert_awaited_once_with(
        "schedule:class:10:date:2026-09-10:lock",
        "owner-token",
        nx=True,
        px=5000,
    )


@pytest.mark.anyio
async def test_cache_releases_fill_lock_only_for_owner_token() -> None:
    client = AsyncMock()
    cache = RedisScheduleCache(client)

    await cache.release_fill_lock(
        class_id=10,
        day=date(2026, 9, 10),
        token="owner-token",
    )

    client.eval.assert_awaited_once_with(
        _RELEASE_LOCK_SCRIPT,
        1,
        "schedule:class:10:date:2026-09-10:lock",
        "owner-token",
    )


@pytest.mark.anyio
async def test_cache_invalidates_requested_class_schedule_days() -> None:
    client = AsyncMock()
    cache = RedisScheduleCache(client)

    await cache.invalidate(
        class_id=10,
        days=(date(2026, 9, 10), date(2026, 9, 11)),
    )

    assert client.eval.await_count == 2
    for call in client.eval.await_args_list:
        script, key_count, key, generation_key = call.args
        assert 'redis.call("INCR", KEYS[2])' in script
        assert key_count == 2
        assert generation_key == f"{key}:gen"


@pytest.mark.anyio
async def test_cache_skips_redis_invalidation_when_no_days_need_invalidation() -> None:
    client = AsyncMock()
    cache = RedisScheduleCache(client)

    await cache.invalidate(class_id=10, days=())

    client.eval.assert_not_called()
