import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest
from aiokafka.structs import TopicPartition

from analytics_service.application.snapshot import LessonSnapshot


class FakeConsumer:
    def __init__(
        self,
        batches: list[dict[TopicPartition, list[SimpleNamespace]]],
    ) -> None:
        self.start = AsyncMock()
        self.stop = AsyncMock()
        self.commit = AsyncMock()
        self.getmany = AsyncMock(side_effect=[*batches, asyncio.CancelledError])


class FakeProducer:
    def __init__(self) -> None:
        self.start = AsyncMock()
        self.stop = AsyncMock()
        self.send_and_wait = AsyncMock()


def snapshot_message(
    *,
    event_id: int = 42,
    lesson_id: int = 501,
    class_id: int = 10,
    teacher_id: int = 100,
    subject_id: int = 1000,
    starts_at: str = "2026-09-20T10:00:00+00:00",
    ends_at: str = "2026-09-20T11:30:00+00:00",
    status: str = "planned",
    version: int = 3,
    partition: int = 0,
    offset: int = 7,
) -> SimpleNamespace:
    return SimpleNamespace(
        topic="schedule.lessons",
        partition=partition,
        offset=offset,
        value=json.dumps(
            {
                "event_id": event_id,
                "event_type": "lesson.snapshot",
                "occurred_at": "2026-09-19T10:00:00+00:00",
                "payload": {
                    "lesson_id": lesson_id,
                    "class_id": class_id,
                    "teacher_id": teacher_id,
                    "subject_id": subject_id,
                    "starts_at": starts_at,
                    "ends_at": ends_at,
                    "status": status,
                    "version": version,
                },
            }
        ).encode(),
    )


def expected_snapshot(
    *,
    event_id: int = 42,
    lesson_id: int = 501,
    class_id: int = 10,
    teacher_id: int = 100,
    subject_id: int = 1000,
    starts_at: datetime = datetime(2026, 9, 20, 10, tzinfo=UTC),
    ends_at: datetime = datetime(2026, 9, 20, 11, 30, tzinfo=UTC),
    status: str = "planned",
    version: int = 3,
) -> LessonSnapshot:
    return LessonSnapshot(
        event_id=event_id,
        occurred_at=datetime(2026, 9, 19, 10, tzinfo=UTC),
        lesson_id=lesson_id,
        class_id=class_id,
        teacher_id=teacher_id,
        subject_id=subject_id,
        starts_at=starts_at,
        ends_at=ends_at,
        status=status,
        version=version,
    )


def configure_worker(
    monkeypatch: pytest.MonkeyPatch,
    consumer: FakeConsumer,
    repository: AsyncMock,
    producer: FakeProducer | None = None,
) -> tuple[Mock, Mock, Mock]:
    from analytics_service.workers import worker

    settings = SimpleNamespace(
        kafka_bootstrap_servers="kafka:19092",
        analytics_dlq_topic="analytics.lesson-snapshots.dlq",
        clickhouse_host="clickhouse",
        clickhouse_port=8123,
        clickhouse_user="default",
        clickhouse_password="change-me",
    )
    consumer_factory = Mock(return_value=consumer)
    producer_factory = Mock(return_value=producer or FakeProducer())
    clickhouse_client = Mock()

    monkeypatch.setattr(worker, "AnalyticsSettings", lambda: settings)
    monkeypatch.setattr(worker, "AIOKafkaConsumer", consumer_factory)
    monkeypatch.setattr(worker, "AIOKafkaProducer", producer_factory)
    monkeypatch.setattr(
        worker.clickhouse_connect, "get_client", Mock(return_value=clickhouse_client)
    )
    monkeypatch.setattr(worker, "ClickHouseSnapshotRepository", lambda _: repository)

    return consumer_factory, producer_factory, worker.clickhouse_connect.get_client


@pytest.mark.anyio
async def test_worker_persists_snapshot_batch_before_committing_partition_offset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    topic_partition = TopicPartition("schedule.lessons", 0)
    consumer = FakeConsumer(
        [
            {
                topic_partition: [
                    snapshot_message(offset=10),
                    snapshot_message(
                        event_id=43,
                        lesson_id=502,
                        class_id=11,
                        teacher_id=101,
                        subject_id=1001,
                        starts_at="2026-09-20T12:00:00+00:00",
                        ends_at="2026-09-20T12:45:00+00:00",
                        status="canceled",
                        version=4,
                        offset=11,
                    ),
                ]
            }
        ]
    )
    repository = AsyncMock()
    consumer_factory, _, clickhouse_client_factory = configure_worker(
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
    first_getmany_call = consumer.getmany.await_args_list[0]
    assert first_getmany_call.args == ()
    assert first_getmany_call.kwargs == {"timeout_ms": 1000, "max_records": 100}
    repository.add_many.assert_awaited_once_with(
        [
            expected_snapshot(),
            expected_snapshot(
                event_id=43,
                lesson_id=502,
                class_id=11,
                teacher_id=101,
                subject_id=1001,
                starts_at=datetime(2026, 9, 20, 12, tzinfo=UTC),
                ends_at=datetime(2026, 9, 20, 12, 45, tzinfo=UTC),
                status="canceled",
                version=4,
            ),
        ]
    )
    consumer.commit.assert_awaited_once_with({topic_partition: 12})
    consumer.stop.assert_awaited_once()


@pytest.mark.anyio
async def test_worker_inserts_snapshots_from_multiple_partitions_in_one_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_partition = TopicPartition("schedule.lessons", 0)
    second_partition = TopicPartition("schedule.lessons", 1)
    consumer = FakeConsumer(
        [
            {
                first_partition: [snapshot_message(offset=10)],
                second_partition: [
                    snapshot_message(
                        event_id=43,
                        lesson_id=502,
                        class_id=11,
                        teacher_id=101,
                        subject_id=1001,
                        starts_at="2026-09-20T12:00:00+00:00",
                        ends_at="2026-09-20T12:45:00+00:00",
                        status="canceled",
                        version=4,
                        partition=1,
                        offset=20,
                    )
                ],
            }
        ]
    )
    repository = AsyncMock()
    configure_worker(monkeypatch, consumer, repository)

    from analytics_service.workers import worker

    with pytest.raises(asyncio.CancelledError):
        await worker.run()

    repository.add_many.assert_awaited_once_with(
        [
            expected_snapshot(),
            expected_snapshot(
                event_id=43,
                lesson_id=502,
                class_id=11,
                teacher_id=101,
                subject_id=1001,
                starts_at=datetime(2026, 9, 20, 12, tzinfo=UTC),
                ends_at=datetime(2026, 9, 20, 12, 45, tzinfo=UTC),
                status="canceled",
                version=4,
            ),
        ]
    )
    consumer.commit.assert_has_awaits(
        [
            call({first_partition: 11}),
            call({second_partition: 21}),
        ]
    )


@pytest.mark.anyio
async def test_worker_does_not_insert_or_commit_empty_poll(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    consumer = FakeConsumer([{}])
    repository = AsyncMock()
    configure_worker(monkeypatch, consumer, repository)

    from analytics_service.workers import worker

    with pytest.raises(asyncio.CancelledError):
        await worker.run()

    repository.add_many.assert_not_awaited()
    consumer.commit.assert_not_awaited()


@pytest.mark.anyio
async def test_worker_commits_ignored_event_partition_without_clickhouse_insert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    topic_partition = TopicPartition("schedule.lessons", 0)
    message = SimpleNamespace(
        topic="schedule.lessons",
        partition=0,
        offset=7,
        value=json.dumps(
            {
                "event_type": "schedule.changed",
                "payload": {"lesson_id": 501},
            }
        ).encode(),
    )
    consumer = FakeConsumer([{topic_partition: [message]}])
    repository = AsyncMock()
    configure_worker(monkeypatch, consumer, repository)

    from analytics_service.workers import worker

    with pytest.raises(asyncio.CancelledError):
        await worker.run()

    repository.add_many.assert_not_awaited()
    consumer.commit.assert_awaited_once_with({topic_partition: 8})


@pytest.mark.anyio
async def test_worker_moves_malformed_event_to_dlq_then_commits_partition_offset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    topic_partition = TopicPartition("schedule.lessons", 0)
    message = SimpleNamespace(
        topic="schedule.lessons",
        partition=0,
        offset=7,
        value=b"not-json",
    )
    consumer = FakeConsumer([{topic_partition: [message]}])
    producer = FakeProducer()
    repository = AsyncMock()
    _, producer_factory, _ = configure_worker(
        monkeypatch, consumer, repository, producer
    )

    from analytics_service.workers import worker

    with pytest.raises(asyncio.CancelledError):
        await worker.run()

    producer_factory.assert_called_once_with(bootstrap_servers="kafka:19092")
    producer.start.assert_awaited_once()
    producer.send_and_wait.assert_awaited_once()
    topic, value = producer.send_and_wait.await_args.args
    assert topic == "analytics.lesson-snapshots.dlq"
    dlq_envelope = json.loads(value)
    failed_at = datetime.fromisoformat(dlq_envelope.pop("failed_at"))
    assert failed_at.tzinfo is UTC
    assert dlq_envelope == {
        "source_topic": "schedule.lessons",
        "source_partition": 0,
        "source_offset": 7,
        "error_type": "JSONDecodeError",
        "error_message": "Expecting value: line 1 column 1 (char 0)",
        "original_value_base64": "bm90LWpzb24=",
    }
    repository.add_many.assert_not_awaited()
    consumer.commit.assert_awaited_once_with({topic_partition: 8})
    producer.stop.assert_awaited_once()
    consumer.stop.assert_awaited_once()


@pytest.mark.anyio
async def test_worker_does_not_commit_when_dlq_publish_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    topic_partition = TopicPartition("schedule.lessons", 0)
    message = SimpleNamespace(
        topic="schedule.lessons",
        partition=0,
        offset=7,
        value=b"not-json",
    )
    consumer = FakeConsumer([{topic_partition: [message]}])
    producer = FakeProducer()
    producer.send_and_wait.side_effect = RuntimeError("Kafka is unavailable")
    repository = AsyncMock()
    configure_worker(monkeypatch, consumer, repository, producer)

    from analytics_service.workers import worker

    with pytest.raises(RuntimeError, match="Kafka is unavailable"):
        await worker.run()

    consumer.commit.assert_not_awaited()
    producer.stop.assert_awaited_once()
    consumer.stop.assert_awaited_once()


@pytest.mark.anyio
async def test_worker_does_not_commit_when_clickhouse_batch_insert_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    topic_partition = TopicPartition("schedule.lessons", 0)
    consumer = FakeConsumer([{topic_partition: [snapshot_message()]}])
    repository = AsyncMock()
    repository.add_many.side_effect = RuntimeError("ClickHouse is unavailable")
    configure_worker(monkeypatch, consumer, repository)

    from analytics_service.workers import worker

    with pytest.raises(RuntimeError, match="ClickHouse is unavailable"):
        await worker.run()

    consumer.commit.assert_not_awaited()
    consumer.stop.assert_awaited_once()
