from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.anyio
async def test_repository_adds_schedule_changed_event_to_session() -> None:
    from schedule_service.domain.events import ScheduleChanged
    from schedule_service.infrastructure.models.outbox_event import OutboxEventRow
    from schedule_service.infrastructure.outbox_repository import (
        SqlAlchemyOutboxRepository,
    )

    session = AsyncMock(spec=AsyncSession)
    repository = SqlAlchemyOutboxRepository(session)

    await repository.add(
        ScheduleChanged(
            lesson_id=501,
            class_id=10,
            affected_dates=(date(2026, 9, 10), date(2026, 9, 11)),
        )
    )

    row = session.add.call_args.args[0]
    assert isinstance(row, OutboxEventRow)
    assert row.event_type == "schedule.changed"
    assert row.payload == {
        "lesson_id": 501,
        "class_id": 10,
        "affected_dates": ["2026-09-10", "2026-09-11"],
    }
    session.add.assert_called_once_with(row)


@pytest.mark.anyio
async def test_repository_adds_lesson_snapshot_event_to_session() -> None:
    from schedule_service.domain.events import LessonSnapshot
    from schedule_service.infrastructure.models.outbox_event import OutboxEventRow
    from schedule_service.infrastructure.outbox_repository import (
        SqlAlchemyOutboxRepository,
    )

    session = AsyncMock(spec=AsyncSession)
    repository = SqlAlchemyOutboxRepository(session)
    event = LessonSnapshot(
        lesson_id=501,
        class_id=10,
        teacher_id=100,
        subject_id=1000,
        starts_at=datetime(2026, 9, 13, 10, tzinfo=UTC),
        ends_at=datetime(2026, 9, 13, 11, tzinfo=UTC),
        status="planned",
        version=4,
    )

    await repository.add(event)

    row = session.add.call_args.args[0]
    assert isinstance(row, OutboxEventRow)
    assert row.event_type == "lesson.snapshot"
    assert row.payload == {
        "lesson_id": 501,
        "class_id": 10,
        "teacher_id": 100,
        "subject_id": 1000,
        "starts_at": "2026-09-13T10:00:00+00:00",
        "ends_at": "2026-09-13T11:00:00+00:00",
        "status": "planned",
        "version": 4,
    }
    session.add.assert_called_once_with(row)


@pytest.mark.anyio
async def test_repository_returns_pending_events_in_id_order() -> None:
    from schedule_service.infrastructure.models.outbox_event import OutboxEventRow
    from schedule_service.infrastructure.outbox_repository import (
        SqlAlchemyOutboxRepository,
    )

    session = AsyncMock(spec=AsyncSession)
    scalar_result = Mock()
    session.scalars.return_value = scalar_result
    scalar_result.all.return_value = [
        OutboxEventRow(
            id=7,
            event_type="lesson.snapshot",
            payload={"lesson_id": 501},
            created_at=datetime(2026, 9, 13, 10, tzinfo=UTC),
        ),
        OutboxEventRow(
            id=8,
            event_type="lesson.snapshot",
            payload={"lesson_id": 502},
            created_at=datetime(2026, 9, 13, 11, tzinfo=UTC),
        ),
    ]
    repository = SqlAlchemyOutboxRepository(session)

    events = await repository.get_pending(limit=100)

    assert [event.id for event in events] == [7, 8]
    assert events[0].event_type == "lesson.snapshot"
    assert events[0].payload == {"lesson_id": 501}
    assert events[0].created_at == datetime(2026, 9, 13, 10, tzinfo=UTC)
    session.scalars.assert_awaited_once()
    statement = session.scalars.await_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "ORDER BY outbox_events.id" in sql


@pytest.mark.anyio
async def test_repository_marks_only_pending_event_as_published() -> None:
    from schedule_service.infrastructure.outbox_repository import (
        SqlAlchemyOutboxRepository,
    )

    session = AsyncMock(spec=AsyncSession)
    repository = SqlAlchemyOutboxRepository(session)

    await repository.mark_published(event_id=7)

    statement = session.execute.await_args.args[0]
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "UPDATE outbox_events SET published_at=now()" in sql
    assert "outbox_events.id = 7" in sql
    assert "outbox_events.published_at IS NULL" in sql
