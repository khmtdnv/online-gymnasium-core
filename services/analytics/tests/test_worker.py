import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from analytics_service.application.snapshot import LessonSnapshot


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


def lesson_snapshot_message() -> SimpleNamespace:
    return SimpleNamespace(
        value=json.dumps(
            {
                "event_id": 42,
                "event_type": "lesson.snapshot",
                "occurred_at": "2026-09-19T10:00:00+00:00",
                "payload": {
                    "lesson_id": 501,
                    "class_id": 10,
                    "teacher_id": 100,
                    "subject_id": 1000,
                    "starts_at": "2026-09-20T10:00:00+00:00",
                    "ends_at": "2026-09-20T11:30:00+00:00",
                    "status": "planned",
                    "version": 3,
                },
            }
        ).encode()
    )


def configure_worker(
    monkeypatch: pytest.MonkeyPatch,
    consumer: FakeConsumer,
    repository: AsyncMock,
) -> Mock:
    from analytics_service.workers import worker

    settings = SimpleNamespace(
        kafka_bootstrap_servers="kafka:19092",
        clickhouse_host="clickhouse",
        clickhouse_port=8123,
        clickhouse_user="default",
        clickhouse_password="change-me",
    )
    consumer_factory = Mock(return_value=consumer)
    clickhouse_client = Mock()

    monkeypatch.setattr(worker, "AnalyticsSettings", lambda: settings)
    monkeypatch.setattr(worker, "AIOKafkaConsumer", consumer_factory)
    monkeypatch.setattr(
        worker.clickhouse_connect, "get_client", Mock(return_value=clickhouse_client)
    )
    monkeypatch.setattr(worker, "ClickHouseSnapshotRepository", lambda _: repository)

    return consumer_factory, worker.clickhouse_connect.get_client


@pytest.mark.anyio
async def test_worker_persists_snapshot_before_committing_offset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    consumer = FakeConsumer([lesson_snapshot_message()])
    repository = AsyncMock()
    consumer_factory, clickhouse_client_factory = configure_worker(
        monkeypatch, consumer, repository
    )

    from analytics_service.workers import worker

    with pytest.raises(asyncio.CancelledError):
        await worker.run()

    consumer_factory.assert_called_once_with(
        "schedule.lessons",
        bootstrap_servers="kafka:19092",
        group_id="schedule-analytics",
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    clickhouse_client_factory.assert_called_once_with(
        host="clickhouse",
        port=8123,
        username="default",
        password="change-me",
    )
    repository.add.assert_awaited_once_with(
        LessonSnapshot(
            event_id=42,
            occurred_at=datetime(2026, 9, 19, 10, tzinfo=UTC),
            lesson_id=501,
            class_id=10,
            teacher_id=100,
            subject_id=1000,
            starts_at=datetime(2026, 9, 20, 10, tzinfo=UTC),
            ends_at=datetime(2026, 9, 20, 11, 30, tzinfo=UTC),
            status="planned",
            version=3,
        )
    )
    consumer.commit.assert_awaited_once()
    consumer.stop.assert_awaited_once()


@pytest.mark.anyio
async def test_worker_commits_unrelated_event_after_deliberate_ignore(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = SimpleNamespace(
        value=json.dumps(
            {
                "event_type": "schedule.changed",
                "payload": {"lesson_id": 501},
            }
        ).encode()
    )
    consumer = FakeConsumer([message])
    repository = AsyncMock()
    configure_worker(monkeypatch, consumer, repository)

    from analytics_service.workers import worker

    with pytest.raises(asyncio.CancelledError):
        await worker.run()

    repository.add.assert_not_awaited()
    consumer.commit.assert_awaited_once()
    consumer.stop.assert_awaited_once()


@pytest.mark.anyio
async def test_worker_does_not_commit_when_clickhouse_insert_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    consumer = FakeConsumer([lesson_snapshot_message()])
    repository = AsyncMock()
    repository.add.side_effect = RuntimeError("ClickHouse is unavailable")
    configure_worker(monkeypatch, consumer, repository)

    from analytics_service.workers import worker

    with pytest.raises(RuntimeError, match="ClickHouse is unavailable"):
        await worker.run()

    consumer.commit.assert_not_awaited()
    consumer.stop.assert_awaited_once()
