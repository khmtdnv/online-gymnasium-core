from datetime import UTC, datetime
from typing import Self

import pytest

from schedule_service.application.ports.outbox_repository import PendingOutboxEvent


class FakeOutboxRepository:
    def __init__(self, events: list[PendingOutboxEvent]) -> None:
        self._events = events
        self.marked_published: list[int] = []

    async def get_pending(self, *, limit: int) -> list[PendingOutboxEvent]:
        return self._events[:limit]

    async def mark_published(self, *, event_id: int) -> None:
        self.marked_published.append(event_id)


class FakeUnitOfWork:
    def __init__(self, outbox: FakeOutboxRepository) -> None:
        self.outbox = outbox
        self.closed = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.closed = True


class FakePublisher:
    def __init__(self, read_uow: FakeUnitOfWork) -> None:
        self._read_uow = read_uow
        self.published: list[int] = []

    async def publish(self, event: PendingOutboxEvent) -> None:
        assert self._read_uow.closed
        self.published.append(event.id)


@pytest.mark.anyio
async def test_relay_publishes_pending_events_after_read_uow_is_closed() -> None:
    from schedule_service.application.outbox_relay import OutboxRelay

    events = [
        PendingOutboxEvent(
            id=7,
            event_type="lesson.snapshot",
            payload={"lesson_id": 501},
            created_at=datetime(2026, 9, 13, 10, tzinfo=UTC),
        ),
        PendingOutboxEvent(
            id=8,
            event_type="lesson.snapshot",
            payload={"lesson_id": 502},
            created_at=datetime(2026, 9, 13, 11, tzinfo=UTC),
        ),
    ]
    outbox = FakeOutboxRepository(events)
    read_uow = FakeUnitOfWork(outbox)
    uows = [read_uow, FakeUnitOfWork(outbox), FakeUnitOfWork(outbox)]
    publisher = FakePublisher(read_uow)
    relay = OutboxRelay(uow_factory=lambda: uows.pop(0), publisher=publisher)

    delivered = await relay.run_once()

    assert delivered == 2
    assert publisher.published == [7, 8]
    assert outbox.marked_published == [7, 8]


@pytest.mark.anyio
async def test_relay_does_not_mark_or_continue_after_publish_failure() -> None:
    from schedule_service.application.outbox_relay import OutboxRelay

    event = PendingOutboxEvent(
        id=7,
        event_type="lesson.snapshot",
        payload={"lesson_id": 501},
        created_at=datetime(2026, 9, 13, 10, tzinfo=UTC),
    )
    outbox = FakeOutboxRepository([event])
    read_uow = FakeUnitOfWork(outbox)

    class FailingPublisher(FakePublisher):
        async def publish(self, event: PendingOutboxEvent) -> None:
            assert self._read_uow.closed
            self.published.append(event.id)
            raise ConnectionError("Kafka is unavailable")

    publisher = FailingPublisher(read_uow)
    relay = OutboxRelay(uow_factory=lambda: read_uow, publisher=publisher)

    with pytest.raises(ConnectionError, match="Kafka is unavailable"):
        await relay.run_once()

    assert publisher.published == [7]
    assert outbox.marked_published == []
