from collections.abc import Callable
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession

from schedule_service.infrastructure.idempotency_repository import SqlAlchemyIdempotencyRepository
from schedule_service.infrastructure.lesson_repository import SqlAlchemyLessonRepository

type AsyncSessionFactory = Callable[[], AsyncSession]


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory: AsyncSessionFactory) -> None:
        self._session_factory = session_factory

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        self.lessons = SqlAlchemyLessonRepository(self._session)
        self.idempotency = SqlAlchemyIdempotencyRepository(self._session)
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        try:
            if exc_type is None:
                await self._session.commit()
            else:
                await self._session.rollback()
        finally:
            await self._session.close()
