from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

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


@pytest.mark.anyio
async def test_repository_get_maps_existing_row_to_domain_lesson() -> None:
    session = AsyncMock(spec=AsyncSession)
    scalar_result = Mock()
    session.scalars.return_value = scalar_result

    row = ScheduledLessonRow(
        id=501,
        class_id=10,
        teacher_id=100,
        subject_id=1000,
        starts_at=datetime(2026, 9, 10, 10, tzinfo=UTC),
        ends_at=datetime(2026, 9, 10, 11, tzinfo=UTC),
        status="planned",
        version=3,
    )
    scalar_result.one_or_none.return_value = row
    repository = SqlAlchemyLessonRepository(session)

    result = await repository.get(501)

    session.scalars.assert_awaited_once()
    assert result == Lesson(
        id=501,
        class_id=10,
        teacher_id=100,
        subject_id=1000,
        starts_at=datetime(2026, 9, 10, 10, tzinfo=UTC),
        ends_at=datetime(2026, 9, 10, 11, tzinfo=UTC),
        status="planned",
        version=3,
    )


@pytest.mark.anyio
async def test_repository_updates_lesson_and_returns_new_version() -> None:
    session = AsyncMock(spec=AsyncSession)
    scalar_result = Mock()
    session.scalars.return_value = scalar_result

    updated_row = ScheduledLessonRow(
        id=501,
        class_id=10,
        teacher_id=100,
        subject_id=1000,
        starts_at=datetime(2026, 9, 10, 12, tzinfo=UTC),
        ends_at=datetime(2026, 9, 10, 13, tzinfo=UTC),
        status="planned",
        version=4,
    )
    scalar_result.one_or_none.return_value = updated_row
    repository = SqlAlchemyLessonRepository(session)

    lesson = Lesson(
        id=501,
        class_id=10,
        teacher_id=100,
        subject_id=1000,
        starts_at=datetime(2026, 9, 10, 12, tzinfo=UTC),
        ends_at=datetime(2026, 9, 10, 13, tzinfo=UTC),
        status="planned",
        version=3,
    )

    result = await repository.update(lesson, expected_version=3)

    session.scalars.assert_awaited_once()
    assert result == Lesson(
        id=501,
        class_id=10,
        teacher_id=100,
        subject_id=1000,
        starts_at=datetime(2026, 9, 10, 12, tzinfo=UTC),
        ends_at=datetime(2026, 9, 10, 13, tzinfo=UTC),
        status="planned",
        version=4,
    )


@pytest.mark.anyio
async def test_repository_update_returns_none_when_version_does_not_match() -> None:
    session = AsyncMock(spec=AsyncSession)
    scalar_result = Mock()
    session.scalars.return_value = scalar_result
    scalar_result.one_or_none.return_value = None
    repository = SqlAlchemyLessonRepository(session)

    lesson = Lesson(
        id=501,
        class_id=10,
        teacher_id=100,
        subject_id=1000,
        starts_at=datetime(2026, 9, 10, 12, tzinfo=UTC),
        ends_at=datetime(2026, 9, 10, 13, tzinfo=UTC),
        status="planned",
        version=3,
    )

    result = await repository.update(lesson, expected_version=2)

    session.scalars.assert_awaited_once()
    assert result is None


@pytest.mark.anyio
async def test_repository_translates_update_integrity_error_to_schedule_conflict() -> None:
    session = AsyncMock(spec=AsyncSession)
    database_error = IntegrityError(
        "UPDATE scheduled_lessons ...",
        {},
        Exception("schedule overlap"),
    )
    session.scalars.side_effect = database_error
    repository = SqlAlchemyLessonRepository(session)

    lesson = Lesson(
        id=501,
        class_id=10,
        teacher_id=100,
        subject_id=1000,
        starts_at=datetime(2026, 9, 10, 12, tzinfo=UTC),
        ends_at=datetime(2026, 9, 10, 13, tzinfo=UTC),
        status="planned",
        version=3,
    )

    with pytest.raises(ScheduleConflict) as error:
        await repository.update(lesson, expected_version=3)

    assert error.value.__cause__ is database_error


@pytest.mark.anyio
async def test_repository_cancels_planned_lesson_and_returns_new_version() -> None:
    session = AsyncMock(spec=AsyncSession)
    scalar_result = Mock()
    session.scalars.return_value = scalar_result
    scalar_result.one_or_none.return_value = ScheduledLessonRow(
        id=501,
        class_id=10,
        teacher_id=100,
        subject_id=1000,
        starts_at=datetime(2026, 9, 10, 10, tzinfo=UTC),
        ends_at=datetime(2026, 9, 10, 11, tzinfo=UTC),
        status="canceled",
        version=4,
    )
    repository = SqlAlchemyLessonRepository(session)
    lesson = Lesson(
        id=501,
        class_id=10,
        teacher_id=100,
        subject_id=1000,
        starts_at=datetime(2026, 9, 10, 10, tzinfo=UTC),
        ends_at=datetime(2026, 9, 10, 11, tzinfo=UTC),
        status="canceled",
        version=3,
    )

    result = await repository.cancel(lesson, expected_version=3)

    session.scalars.assert_awaited_once()
    assert result == Lesson(
        id=501,
        class_id=10,
        teacher_id=100,
        subject_id=1000,
        starts_at=datetime(2026, 9, 10, 10, tzinfo=UTC),
        ends_at=datetime(2026, 9, 10, 11, tzinfo=UTC),
        status="canceled",
        version=4,
    )


@pytest.mark.anyio
async def test_repository_cancel_returns_none_when_row_is_no_longer_planned() -> None:
    session = AsyncMock(spec=AsyncSession)
    scalar_result = Mock()
    session.scalars.return_value = scalar_result
    scalar_result.one_or_none.return_value = None
    repository = SqlAlchemyLessonRepository(session)
    lesson = Lesson(
        id=501,
        class_id=10,
        teacher_id=100,
        subject_id=1000,
        starts_at=datetime(2026, 9, 10, 10, tzinfo=UTC),
        ends_at=datetime(2026, 9, 10, 11, tzinfo=UTC),
        status="canceled",
        version=3,
    )

    result = await repository.cancel(lesson, expected_version=3)

    assert result is None
