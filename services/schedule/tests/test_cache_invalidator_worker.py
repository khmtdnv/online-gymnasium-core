import asyncio
import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from schedule_service.domain.events import ScheduleChanged


class FakeConsumer:
    def __init__(self, messages: list[SimpleNamespace]) -> None:
        self._messages = messages
        self.start = AsyncMock()
        self.stop = AsyncMock()
        self.commit = AsyncMock()

    async def __aiter__(self):
        for message in self._messages:
            yield message
        raise asyncio.CancelledError


def configure_worker(
    monkeypatch: pytest.MonkeyPatch,
    consumer: FakeConsumer,
    invalidator: AsyncMock,
    cache: AsyncMock,
) -> Mock:
    from schedule_service.workers import cache_invalidator

    settings = SimpleNamespace(
        kafka_bootstrap_servers="kafka:19092",
        redis_url="redis://redis:6379/0",
    )
    consumer_factory = Mock(return_value=consumer)

    monkeypatch.setattr(cache_invalidator, "InvalidatorSettings", lambda: settings)
    monkeypatch.setattr(cache_invalidator, "AIOKafkaConsumer", consumer_factory)
    monkeypatch.setattr(cache_invalidator.redis, "from_url", Mock())
    monkeypatch.setattr(cache_invalidator, "RedisScheduleCache", lambda _: cache)
    monkeypatch.setattr(cache_invalidator, "CacheInvalidator", lambda _: invalidator)

    return consumer_factory


@pytest.mark.anyio
async def test_worker_invalidates_changed_schedule_before_committing_offset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from schedule_service.workers import cache_invalidator

    message = SimpleNamespace(
        value=json.dumps(
            {
                "event_type": "schedule.changed",
                "payload": {
                    "lesson_id": 501,
                    "class_id": 10,
                    "affected_dates": ["2026-09-10", "2026-09-11"],
                },
            }
        ).encode()
    )
    consumer = FakeConsumer([message])
    invalidator = AsyncMock()
    cache = AsyncMock()
    consumer_factory = configure_worker(monkeypatch, consumer, invalidator, cache)

    with pytest.raises(asyncio.CancelledError):
        await cache_invalidator.run()

    consumer_factory.assert_called_once_with(
        "schedule.lessons",
        bootstrap_servers="kafka:19092",
        group_id="schedule-cache-invalidator",
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    invalidator.handle.assert_awaited_once_with(
        ScheduleChanged(
            lesson_id=501,
            class_id=10,
            affected_dates=(date(2026, 9, 10), date(2026, 9, 11)),
        )
    )
    consumer.commit.assert_awaited_once()
    consumer.stop.assert_awaited_once()
    cache.aclose.assert_awaited_once()


@pytest.mark.anyio
async def test_worker_commits_unrelated_event_without_invalidating_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from schedule_service.workers import cache_invalidator

    message = SimpleNamespace(
        value=json.dumps(
            {
                "event_type": "lesson.created",
                "payload": {"lesson_id": 501},
            }
        ).encode()
    )
    consumer = FakeConsumer([message])
    invalidator = AsyncMock()
    cache = AsyncMock()
    configure_worker(monkeypatch, consumer, invalidator, cache)

    with pytest.raises(asyncio.CancelledError):
        await cache_invalidator.run()

    invalidator.handle.assert_not_awaited()
    consumer.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_worker_does_not_commit_when_cache_invalidation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from schedule_service.workers import cache_invalidator

    message = SimpleNamespace(
        value=json.dumps(
            {
                "event_type": "schedule.changed",
                "payload": {
                    "lesson_id": 501,
                    "class_id": 10,
                    "affected_dates": ["2026-09-10"],
                },
            }
        ).encode()
    )
    consumer = FakeConsumer([message])
    invalidator = AsyncMock()
    invalidator.handle.side_effect = RuntimeError("Redis is unavailable")
    cache = AsyncMock()
    configure_worker(monkeypatch, consumer, invalidator, cache)

    with pytest.raises(RuntimeError, match="Redis is unavailable"):
        await cache_invalidator.run()

    consumer.commit.assert_not_awaited()
    consumer.stop.assert_awaited_once()
    cache.aclose.assert_awaited_once()
