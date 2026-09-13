from collections.abc import Callable
from typing import Protocol, Self

from schedule_service.application.ports.idempotency_repository import IdempotencyRepository
from schedule_service.application.ports.lesson_repository import LessonRepository
from schedule_service.application.ports.outbox_repository import OutboxRepository


class UnitOfWork(Protocol):
    lessons: LessonRepository
    idempotency: IdempotencyRepository
    outbox: OutboxRepository

    async def __aenter__(self) -> Self: ...

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None: ...


type UnitOfWorkFactory = Callable[[], UnitOfWork]
