from collections.abc import Callable
from typing import Protocol, Self

from schedule_service.application.ports.lesson_repository import LessonRepository


class UnitOfWork(Protocol):
    lessons: LessonRepository

    async def __aenter__(self) -> Self: ...

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None: ...


type UnitOfWorkFactory = Callable[[], UnitOfWork]
