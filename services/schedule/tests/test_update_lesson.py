from datetime import UTC, datetime
from typing import Self

import pytest

from schedule_service.application.update_lesson import (
    UpdateLessonCommand,
    UpdateLessonHandler,
)
from schedule_service.domain.lesson import Lesson


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
        self.updated: tuple[Lesson, int] | None = None

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

    async def update(self, lesson: Lesson, expected_version: int):
        self.updated = (lesson, expected_version)

        if self.saved.version == expected_version:
            self.saved.starts_at = lesson.starts_at
            self.saved.ends_at = lesson.ends_at
            self.saved.version = lesson.version + 1
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

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


@pytest.mark.anyio
async def test_handler_reschedules_lesson_through_uow() -> None:

    command = UpdateLessonCommand(
        lesson_id=501,
        starts_at=datetime(2026, 9, 10, 12, tzinfo=UTC),
        ends_at=datetime(2026, 9, 10, 13, tzinfo=UTC),
        expected_version=3,
    )
    fake_uow = FakeUnitOfWork()
    handler = UpdateLessonHandler(uow_factory=lambda: fake_uow)

    updated_lesson = await handler.handle(command)

    assert updated_lesson.id == 501
    assert updated_lesson.version == 4
    assert updated_lesson.starts_at == command.starts_at
    assert updated_lesson.ends_at == command.ends_at

    assert fake_uow.lessons.updated is not None
    lesson_sent_to_update, expected_version = fake_uow.lessons.updated
    assert expected_version == 3
    assert lesson_sent_to_update.starts_at == command.starts_at
    assert lesson_sent_to_update.ends_at == command.ends_at
    assert lesson_sent_to_update.class_id == 10
    assert lesson_sent_to_update.teacher_id == 100
    assert lesson_sent_to_update.subject_id == 1000


@pytest.mark.anyio
async def test_handler_raises_not_found_when_lesson_does_not_exist() -> None:
    from schedule_service.application.errors import LessonNotFound

    fake_uow = FakeUnitOfWork()
    handler = UpdateLessonHandler(uow_factory=lambda: fake_uow)
    command = UpdateLessonCommand(
        lesson_id=404,
        starts_at=datetime(2026, 9, 10, 12, tzinfo=UTC),
        ends_at=datetime(2026, 9, 10, 13, tzinfo=UTC),
        expected_version=3,
    )

    with pytest.raises(LessonNotFound):
        await handler.handle(command)

    assert fake_uow.lessons.updated is None


@pytest.mark.anyio
async def test_handler_raises_version_conflict_for_stale_version() -> None:
    from schedule_service.application.errors import VersionConflict

    fake_uow = FakeUnitOfWork()
    handler = UpdateLessonHandler(uow_factory=lambda: fake_uow)
    command = UpdateLessonCommand(
        lesson_id=501,
        starts_at=datetime(2026, 9, 10, 12, tzinfo=UTC),
        ends_at=datetime(2026, 9, 10, 13, tzinfo=UTC),
        expected_version=2,
    )

    with pytest.raises(VersionConflict):
        await handler.handle(command)

    assert fake_uow.lessons.updated is not None
    _, expected_version = fake_uow.lessons.updated
    assert expected_version == 2

    assert fake_uow.lessons.saved.starts_at == datetime(2026, 9, 10, 10, tzinfo=UTC)
    assert fake_uow.lessons.saved.ends_at == datetime(2026, 9, 10, 11, tzinfo=UTC)
    assert fake_uow.lessons.saved.version == 3
