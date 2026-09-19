from datetime import UTC, date, datetime
from typing import Self

import pytest

from schedule_service.domain.events import LessonSnapshot, ScheduleChanged
from schedule_service.domain.lesson import Lesson


class FakeOutboxRepository:
    def __init__(self) -> None:
        self.events: list[object] = []

    async def add(self, event: object) -> None:
        self.events.append(event)


class FakeLessonRepository:
    def __init__(self) -> None:
        self.saved = Lesson(
            id=501,
            class_id=10,
            teacher_id=100,
            subject_id=1000,
            starts_at=datetime(2026, 9, 10, 10, tzinfo=UTC),
            ends_at=datetime(2026, 9, 10, 11, tzinfo=UTC),
            status="planned",
            version=3,
        )

    async def get(self, lesson_id: int) -> Lesson | None:
        if lesson_id != self.saved.id:
            return None
        return Lesson(
            id=self.saved.id,
            class_id=self.saved.class_id,
            teacher_id=self.saved.teacher_id,
            subject_id=self.saved.subject_id,
            starts_at=self.saved.starts_at,
            ends_at=self.saved.ends_at,
            status=self.saved.status,
            version=self.saved.version,
        )

    async def cancel(self, lesson: Lesson, expected_version: int) -> Lesson | None:
        if self.saved.version != expected_version or self.saved.status != "planned":
            return None
        self.saved.status = lesson.status
        self.saved.version += 1
        return Lesson(
            id=self.saved.id,
            class_id=self.saved.class_id,
            teacher_id=self.saved.teacher_id,
            subject_id=self.saved.subject_id,
            starts_at=self.saved.starts_at,
            ends_at=self.saved.ends_at,
            status=self.saved.status,
            version=self.saved.version,
        )


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.lessons = FakeLessonRepository()
        self.outbox = FakeOutboxRepository()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


@pytest.mark.anyio
async def test_handler_cancels_planned_lesson() -> None:
    from schedule_service.application.cancel_lesson import (
        CancelLessonCommand,
        CancelLessonHandler,
    )

    fake_uow = FakeUnitOfWork()
    handler = CancelLessonHandler(uow_factory=lambda: fake_uow)

    result = await handler.handle(
        CancelLessonCommand(lesson_id=501, expected_version=3)
    )

    assert result.id == 501
    assert result.status == "canceled"
    assert result.version == 4
    assert fake_uow.lessons.saved.status == "canceled"
    assert fake_uow.lessons.saved.version == 4
    assert fake_uow.outbox.events == [
        ScheduleChanged(
            lesson_id=501,
            class_id=10,
            affected_dates=(date(2026, 9, 10),),
        ),
        LessonSnapshot(
            lesson_id=501,
            class_id=10,
            teacher_id=100,
            subject_id=1000,
            starts_at=datetime(2026, 9, 10, 10, tzinfo=UTC),
            ends_at=datetime(2026, 9, 10, 11, tzinfo=UTC),
            status="canceled",
            version=4,
        ),
    ]


@pytest.mark.anyio
async def test_handler_raises_not_found_for_absent_lesson() -> None:
    from schedule_service.application.cancel_lesson import (
        CancelLessonCommand,
        CancelLessonHandler,
    )
    from schedule_service.application.errors import LessonNotFound

    fake_uow = FakeUnitOfWork()
    handler = CancelLessonHandler(uow_factory=lambda: fake_uow)

    with pytest.raises(LessonNotFound):
        await handler.handle(CancelLessonCommand(lesson_id=404, expected_version=3))


@pytest.mark.anyio
async def test_handler_raises_version_conflict_for_stale_version() -> None:
    from schedule_service.application.cancel_lesson import (
        CancelLessonCommand,
        CancelLessonHandler,
    )
    from schedule_service.application.errors import VersionConflict

    fake_uow = FakeUnitOfWork()
    handler = CancelLessonHandler(uow_factory=lambda: fake_uow)

    with pytest.raises(VersionConflict):
        await handler.handle(CancelLessonCommand(lesson_id=501, expected_version=2))
