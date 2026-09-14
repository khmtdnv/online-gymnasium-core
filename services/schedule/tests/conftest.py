from datetime import date
from typing import Never

import pytest

from schedule_service.application.ports.unit_of_work import UnitOfWorkFactory
from schedule_service.domain.lesson import Lesson


class NoopScheduleCache:
    async def get(self, *, class_id: int, day: date) -> list[Lesson] | None:
        return None

    async def get_generation(self, *, class_id: int, day: date) -> int:
        return 0

    async def try_acquire_fill_lock(
        self,
        *,
        class_id: int,
        day: date,
        token: str,
        ttl_ms: int,
    ) -> bool:
        return True

    async def release_fill_lock(
        self,
        *,
        class_id: int,
        day: date,
        token: str,
    ) -> None:
        return None

    async def set_if_generation(
        self,
        *,
        class_id: int,
        day: date,
        lessons: list[Lesson],
        ttl_seconds: int,
        expected_generation: int,
    ) -> bool:
        return True

    async def invalidate(self, *, class_id: int, days: tuple[date, ...]) -> None:
        return None

    async def aclose(self) -> None:
        return None


@pytest.fixture
def unused_uow_factory() -> UnitOfWorkFactory:
    def factory() -> Never:
        raise AssertionError("This test must not create a UnitOfWork")

    return factory
