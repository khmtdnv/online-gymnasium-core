from types import TracebackType
from typing import Protocol, Self

from gateway_service.application.ports.user_repository import UserRepository


class UnitOfWork(Protocol):
    users: UserRepository

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...
