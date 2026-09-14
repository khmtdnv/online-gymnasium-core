import json
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import pytest

from schedule_service.domain.lesson import Lesson
from schedule_service.infrastructure.redis_schedule_cache import RedisScheduleCache


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
async def test_cache_stores_lessons_as_json_with_requested_ttl() -> None:
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

    await cache.set(
        class_id=10,
        day=date(2026, 9, 10),
        lessons=lessons,
        ttl_seconds=60,
    )

    key, serialized = client.set.await_args.args
    assert key == "schedule:class:10:date:2026-09-10"
    assert client.set.await_args.kwargs == {"ex": 60}
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
async def test_cache_invalidates_requested_class_schedule_days() -> None:
    client = AsyncMock()
    cache = RedisScheduleCache(client)

    await cache.invalidate(
        class_id=10,
        days=(date(2026, 9, 10), date(2026, 9, 11)),
    )

    client.delete.assert_awaited_once_with(
        "schedule:class:10:date:2026-09-10",
        "schedule:class:10:date:2026-09-11",
    )


@pytest.mark.anyio
async def test_cache_skips_redis_delete_when_no_days_need_invalidation() -> None:
    client = AsyncMock()
    cache = RedisScheduleCache(client)

    await cache.invalidate(class_id=10, days=())

    client.delete.assert_not_called()
