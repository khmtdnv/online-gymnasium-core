from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from schedule_service.application.errors import ScheduleConflict
from schedule_service.domain.lesson import Lesson
from schedule_service.infrastructure.lesson_repository import SqlAlchemyLessonRepository
from schedule_service.infrastructure.models.scheduled_lesson import ScheduledLessonRow


@pytest.mark.anyio
async def test_repository_adds_flushes_refreshes_and_maps_lesson() -> None:

    session = AsyncMock(spec=AsyncSession)

    async def assign_database_values(row: ScheduledLessonRow) -> None:
        row.id = 501
        row.status = "planned"
        row.version = 1

    session.refresh.side_effect = assign_database_values
    repository = SqlAlchemyLessonRepository(session)
    lesson = Lesson.create(
        class_id=10,
        teacher_id=100,
        subject_id=1000,
        starts_at=datetime(2026, 9, 10, 10, tzinfo=UTC),
        ends_at=datetime(2026, 9, 10, 11, tzinfo=UTC),
    )

    result = await repository.add(lesson)

    row = session.add.call_args.args[0]
    assert isinstance(row, ScheduledLessonRow)
    assert row.class_id == lesson.class_id
    assert row.teacher_id == lesson.teacher_id
    assert row.subject_id == lesson.subject_id
    assert row.starts_at == lesson.starts_at
    assert row.ends_at == lesson.ends_at

    session.add.assert_called_once_with(row)
    session.flush.assert_awaited_once()
    session.refresh.assert_awaited_once_with(row)

    assert result == Lesson(
        class_id=10,
        teacher_id=100,
        subject_id=1000,
        starts_at=lesson.starts_at,
        ends_at=lesson.ends_at,
        id=501,
        status="planned",
        version=1,
    )


@pytest.mark.anyio
async def test_repository_translates_integrity_error_to_schedule_conflict() -> None:
    session = AsyncMock(spec=AsyncSession)
    database_error = IntegrityError(
        "INSERT INTO scheduled_lessons ...",
        {},
        Exception("schedule overlap"),
    )
    session.flush.side_effect = database_error
    repository = SqlAlchemyLessonRepository(session)
    lesson = Lesson.create(
        class_id=10,
        teacher_id=100,
        subject_id=1000,
        starts_at=datetime(2026, 9, 10, 10, tzinfo=UTC),
        ends_at=datetime(2026, 9, 10, 11, tzinfo=UTC),
    )
    with pytest.raises(ScheduleConflict) as error:
        await repository.add(lesson)

    session.refresh.assert_not_awaited()
    assert error.value.__cause__ is database_error
