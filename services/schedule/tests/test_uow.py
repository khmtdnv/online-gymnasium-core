from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.anyio
async def test_uow_commits_and_closes_session_after_success() -> None:
    from schedule_service.infrastructure.idempotency_repository import (
        SqlAlchemyIdempotencyRepository,
    )
    from schedule_service.infrastructure.lesson_repository import (
        SqlAlchemyLessonRepository,
    )
    from schedule_service.infrastructure.outbox_repository import (
        SqlAlchemyOutboxRepository,
    )
    from schedule_service.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

    session = AsyncMock(spec=AsyncSession)
    uow = SqlAlchemyUnitOfWork(session_factory=lambda: session)

    async with uow:
        assert isinstance(uow.lessons, SqlAlchemyLessonRepository)
        assert isinstance(uow.idempotency, SqlAlchemyIdempotencyRepository)
        assert isinstance(uow.outbox, SqlAlchemyOutboxRepository)

    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()
    session.close.assert_awaited_once()


@pytest.mark.anyio
async def test_uow_rolls_back_and_closes_session_after_error() -> None:
    from schedule_service.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

    session = AsyncMock(spec=AsyncSession)
    uow = SqlAlchemyUnitOfWork(session_factory=lambda: session)

    with pytest.raises(RuntimeError, match="boom"):
        async with uow:
            raise RuntimeError("boom")

    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()
    session.close.assert_awaited_once()
