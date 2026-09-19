from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Self

import pytest

from schedule_service.domain.events import LessonSnapshot, ScheduleChanged
from schedule_service.domain.lesson import Lesson


@dataclass
class FakeIdempotencyRecord:
    request_hash: str
    lesson: Lesson | None = None


class FakeIdempotencyRepository:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], FakeIdempotencyRecord] = {}

    async def claim(
        self, operation: str, key: str, request_hash: str
    ) -> FakeIdempotencyRecord | None:
        record = self.records.get((operation, key))

        if record is None:
            self.records[(operation, key)] = FakeIdempotencyRecord(
                request_hash=request_hash
            )
            return None

        return record

    async def complete(self, operation: str, key: str, lesson: Lesson) -> None:
        record = self.records.get((operation, key))
        assert record is not None
        record.lesson = lesson


class FakeLessonRepository:
    def __init__(self) -> None:
        self.add_calls = 0
        self.saved: Lesson | None = None

    async def add(self, lesson: Lesson) -> Lesson:
        self.add_calls += 1
        self.saved = lesson

        return Lesson(
            id=501,
            class_id=lesson.class_id,
            teacher_id=lesson.teacher_id,
            subject_id=lesson.subject_id,
            starts_at=lesson.starts_at,
            ends_at=lesson.ends_at,
            status=lesson.status,
            version=lesson.version,
        )


class FakeOutboxRepository:
    def __init__(self) -> None:
        self.events: list[object] = []

    async def add(self, event: object) -> None:
        self.events.append(event)


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.lessons = FakeLessonRepository()
        self.idempotency = FakeIdempotencyRepository()
        self.outbox = FakeOutboxRepository()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


@pytest.mark.anyio
async def test_handler_creates_lesson_through_uow() -> None:
    from schedule_service.application.create_lesson import (
        CreateLessonCommand,
        CreateLessonHandler,
    )

    fake_uow = FakeUnitOfWork()
    handler = CreateLessonHandler(uow_factory=lambda: fake_uow)

    command = CreateLessonCommand(
        class_id=1,
        teacher_id=2,
        subject_id=3,
        starts_at=datetime(2026, 9, 10, 11, 30, tzinfo=UTC),
        ends_at=datetime(2026, 9, 10, 12, 15, tzinfo=UTC),
    )

    result = await handler.handle(command)

    assert result.id == 501
    assert fake_uow.lessons.saved is not None

    saved = fake_uow.lessons.saved
    assert saved.class_id == 1
    assert saved.teacher_id == 2
    assert saved.subject_id == 3
    assert saved.starts_at == command.starts_at
    assert saved.ends_at == command.ends_at
    assert saved.status == "planned"
    assert saved.version == 1


@pytest.mark.anyio
async def test_handler_queues_lesson_snapshot_after_creating_lesson() -> None:
    from schedule_service.application.create_lesson import (
        CreateLessonCommand,
        CreateLessonHandler,
    )

    fake_uow = FakeUnitOfWork()
    handler = CreateLessonHandler(uow_factory=lambda: fake_uow)
    command = CreateLessonCommand(
        class_id=10,
        teacher_id=100,
        subject_id=1000,
        starts_at=datetime(2026, 9, 13, 10, tzinfo=UTC),
        ends_at=datetime(2026, 9, 13, 11, tzinfo=UTC),
    )

    await handler.handle(command)

    assert len(fake_uow.outbox.events) == 2
    schedule_changed, lesson_snapshot = fake_uow.outbox.events
    assert schedule_changed == ScheduleChanged(
        lesson_id=501,
        class_id=10,
        affected_dates=(date(2026, 9, 13),),
    )
    assert lesson_snapshot == LessonSnapshot(
        lesson_id=501,
        class_id=10,
        teacher_id=100,
        subject_id=1000,
        starts_at=command.starts_at,
        ends_at=command.ends_at,
        status="planned",
        version=1,
    )


@pytest.mark.anyio
async def test_same_requests_are_idempotent() -> None:
    from schedule_service.application.create_lesson import (
        CreateLessonCommand,
        CreateLessonHandler,
    )

    fake_uow = FakeUnitOfWork()
    handler = CreateLessonHandler(uow_factory=lambda: fake_uow)

    first_command = CreateLessonCommand(
        class_id=1,
        teacher_id=2,
        subject_id=3,
        starts_at=datetime(2026, 9, 10, 11, 30, tzinfo=UTC),
        ends_at=datetime(2026, 9, 10, 12, 15, tzinfo=UTC),
        idempotency_key="k1",
        request_hash="h1",
    )

    second_command = CreateLessonCommand(
        class_id=1,
        teacher_id=2,
        subject_id=3,
        starts_at=datetime(2026, 9, 10, 11, 30, tzinfo=UTC),
        ends_at=datetime(2026, 9, 10, 12, 15, tzinfo=UTC),
        idempotency_key="k1",
        request_hash="h1",
    )

    first_cmd_result = await handler.handle(first_command)
    second_cmd_result = await handler.handle(second_command)

    assert fake_uow.lessons.add_calls == 1
    assert len(fake_uow.outbox.events) == 2

    assert first_cmd_result == second_cmd_result


@pytest.mark.anyio
async def test_same_requests_with_different_hash_raises_error() -> None:
    from schedule_service.application.create_lesson import (
        CreateLessonCommand,
        CreateLessonHandler,
    )
    from schedule_service.application.errors import IdempotencyKeyReuse

    fake_uow = FakeUnitOfWork()
    handler = CreateLessonHandler(uow_factory=lambda: fake_uow)

    first_command = CreateLessonCommand(
        class_id=1,
        teacher_id=2,
        subject_id=3,
        starts_at=datetime(2026, 9, 10, 11, 30, tzinfo=UTC),
        ends_at=datetime(2026, 9, 10, 12, 15, tzinfo=UTC),
        idempotency_key="k1",
        request_hash="h1",
    )

    second_command = CreateLessonCommand(
        class_id=1,
        teacher_id=2,
        subject_id=3,
        starts_at=datetime(2026, 9, 10, 11, 30, tzinfo=UTC),
        ends_at=datetime(2026, 9, 10, 12, 15, tzinfo=UTC),
        idempotency_key="k1",
        request_hash="h2",
    )

    await handler.handle(first_command)
    with pytest.raises(IdempotencyKeyReuse):
        await handler.handle(second_command)

    assert fake_uow.lessons.add_calls == 1
