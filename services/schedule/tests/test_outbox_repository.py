from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.anyio
async def test_repository_adds_json_snapshot_of_lesson_created_event_to_session() -> None:
    from schedule_service.domain.events import LessonCreated
    from schedule_service.infrastructure.models.outbox_event import OutboxEventRow
    from schedule_service.infrastructure.outbox_repository import SqlAlchemyOutboxRepository

    session = AsyncMock(spec=AsyncSession)
    repository = SqlAlchemyOutboxRepository(session)
    event = LessonCreated(
        lesson_id=501,
        class_id=10,
        teacher_id=100,
        subject_id=1000,
        starts_at=datetime(2026, 9, 13, 10, tzinfo=UTC),
        ends_at=datetime(2026, 9, 13, 11, tzinfo=UTC),
        status="planned",
        version=1,
    )

    await repository.add(event)

    row = session.add.call_args.args[0]
    assert isinstance(row, OutboxEventRow)
    assert row.event_type == "lesson.created"
    assert row.payload == {
        "id": 501,
        "class_id": 10,
        "teacher_id": 100,
        "subject_id": 1000,
        "starts_at": "2026-09-13T10:00:00+00:00",
        "ends_at": "2026-09-13T11:00:00+00:00",
        "status": "planned",
        "version": 1,
    }
    session.add.assert_called_once_with(row)
