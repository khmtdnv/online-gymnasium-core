import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from gateway_service.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from gateway_service.infrastructure.user_repository import SqlAlchemyUserRepository


def test_unit_of_work_commits_and_closes_session_after_success() -> None:
    session = AsyncMock(spec=AsyncSession)
    session_factory = Mock(return_value=session)

    async def run() -> None:
        async with SqlAlchemyUnitOfWork(session_factory) as uow:
            assert isinstance(uow.users, SqlAlchemyUserRepository)

    asyncio.run(run())

    session_factory.assert_called_once_with()
    session.commit.assert_awaited_once_with()
    session.rollback.assert_not_awaited()
    session.close.assert_awaited_once_with()


def test_unit_of_work_rolls_back_and_closes_session_after_error() -> None:
    session = AsyncMock(spec=AsyncSession)
    session_factory = Mock(return_value=session)

    async def run() -> None:
        async with SqlAlchemyUnitOfWork(session_factory):
            raise ValueError("reject refresh")

    with pytest.raises(ValueError, match="reject refresh"):
        asyncio.run(run())

    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once_with()
    session.close.assert_awaited_once_with()


def test_unit_of_work_closes_session_when_commit_fails() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.commit.side_effect = RuntimeError("commit failed")
    session_factory = Mock(return_value=session)

    async def run() -> None:
        async with SqlAlchemyUnitOfWork(session_factory):
            pass

    with pytest.raises(RuntimeError, match="commit failed"):
        asyncio.run(run())

    session.close.assert_awaited_once_with()
