from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from schedule_service.application.ports.idempotency_repository import IdempotencyRecord
from schedule_service.domain.lesson import Lesson
from schedule_service.infrastructure.idempotency_repository import SqlAlchemyIdempotencyRepository
from schedule_service.infrastructure.models.idempotency_request import IdempotencyRequestRow
from schedule_service.infrastructure.models.scheduled_lesson import ScheduledLessonRow


@pytest.mark.anyio
async def test_repository_claim_returns_none_for_new_key() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = 1
    repository = SqlAlchemyIdempotencyRepository(session)

    result = await repository.claim(
        operation="create_lesson",
        key="k1",
        request_hash="h1",
    )

    assert result is None
    session.scalar.assert_awaited_once()


@pytest.mark.anyio
async def test_repository_claim_returns_existing_completed_lesson() -> None:
    session = AsyncMock(spec=AsyncSession)
    existing_record = IdempotencyRequestRow(
        id=1,
        operation="create_lesson",
        idempotency_key="k1",
        request_hash="h1",
        lesson_id=501,
    )
    existing_lesson = ScheduledLessonRow(
        id=501,
        class_id=10,
        teacher_id=100,
        subject_id=1000,
        starts_at=datetime(2026, 9, 13, 10, tzinfo=UTC),
        ends_at=datetime(2026, 9, 13, 11, tzinfo=UTC),
        status="planned",
        version=1,
    )
    session.scalar.side_effect = [None, existing_record, existing_lesson]
    repository = SqlAlchemyIdempotencyRepository(session)

    result = await repository.claim(
        operation="create_lesson",
        key="k1",
        request_hash="different-incoming-hash",
    )

    assert result == IdempotencyRecord(
        request_hash="h1",
        lesson=Lesson(
            id=501,
            class_id=10,
            teacher_id=100,
            subject_id=1000,
            starts_at=datetime(2026, 9, 13, 10, tzinfo=UTC),
            ends_at=datetime(2026, 9, 13, 11, tzinfo=UTC),
            status="planned",
            version=1,
        ),
    )
    assert session.scalar.await_count == 3


@pytest.mark.anyio
async def test_repository_complete_updates_claimed_record() -> None:
    session = AsyncMock(spec=AsyncSession)
    repository = SqlAlchemyIdempotencyRepository(session)
    lesson = Lesson(
        id=501,
        class_id=10,
        teacher_id=100,
        subject_id=1000,
        starts_at=datetime(2026, 9, 13, 10, tzinfo=UTC),
        ends_at=datetime(2026, 9, 13, 11, tzinfo=UTC),
        status="planned",
        version=1,
    )

    await repository.complete(
        operation="create_lesson",
        key="k1",
        lesson=lesson,
    )

    session.execute.assert_awaited_once()
