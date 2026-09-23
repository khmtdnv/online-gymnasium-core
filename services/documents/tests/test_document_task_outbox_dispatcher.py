from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Self
from uuid import UUID, uuid4

import pytest


@dataclass(frozen=True, slots=True)
class PendingDocumentTask:
    id: UUID
    document_job_id: UUID
    task_name: str
    created_at: datetime


@dataclass
class FakeOutboxRepository:
    pending: list[PendingDocumentTask]
    marked_published: list[UUID] = field(default_factory=list)

    def get_pending(self, *, limit: int) -> list[PendingDocumentTask]:
        return self.pending[:limit]

    def mark_published(self, *, task_id: UUID) -> None:
        self.marked_published.append(task_id)


class FakeUnitOfWork:
    def __init__(self, outbox: FakeOutboxRepository) -> None:
        self.outbox = outbox

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        return None


class FakeTaskPublisher:
    def __init__(self) -> None:
        self.published: list[PendingDocumentTask] = []

    def publish(self, task: PendingDocumentTask) -> None:
        self.published.append(task)


def pending_task() -> PendingDocumentTask:
    return PendingDocumentTask(
        id=uuid4(),
        document_job_id=uuid4(),
        task_name="documents.generate_certificate",
        created_at=datetime(2026, 9, 22, tzinfo=UTC),
    )


def test_dispatcher_publishes_pending_task_then_marks_it_published() -> None:
    from document_service.application.document_task_outbox_dispatcher import (
        DocumentTaskOutboxDispatcher,
    )

    task = pending_task()
    outbox = FakeOutboxRepository(pending=[task])
    publisher = FakeTaskPublisher()
    uows = [FakeUnitOfWork(outbox), FakeUnitOfWork(outbox)]
    dispatcher = DocumentTaskOutboxDispatcher(
        uow_factory=lambda: uows.pop(0),
        publisher=publisher,
    )

    processed = dispatcher.run_once()

    assert processed == 1
    assert publisher.published == [task]
    assert outbox.marked_published == [task.id]


def test_dispatcher_leaves_task_unpublished_when_broker_send_fails() -> None:
    from document_service.application.document_task_outbox_dispatcher import (
        DocumentTaskOutboxDispatcher,
    )

    class FailingTaskPublisher:
        def publish(self, task: PendingDocumentTask) -> None:
            raise ConnectionError("RabbitMQ is unavailable")

    task = pending_task()
    outbox = FakeOutboxRepository(pending=[task])
    dispatcher = DocumentTaskOutboxDispatcher(
        uow_factory=lambda: FakeUnitOfWork(outbox),
        publisher=FailingTaskPublisher(),
    )

    with pytest.raises(ConnectionError, match="RabbitMQ is unavailable"):
        dispatcher.run_once()

    assert outbox.marked_published == []
