from datetime import UTC, datetime
from typing import Self

import pytest

from schedule_service.domain.lesson import Lesson


class FakeLessonRepository:
    def __init__(self) -> None:
        self.saved: Lesson | None = None

    async def add(self, lesson: Lesson) -> Lesson:
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


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.lessons = FakeLessonRepository()

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
