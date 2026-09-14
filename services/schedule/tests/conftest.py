from datetime import date
from typing import Never

import pytest

from schedule_service.application.ports.unit_of_work import UnitOfWorkFactory
from schedule_service.domain.lesson import Lesson


class NoopScheduleCache:
    async def get(self, *, class_id: int, day: date) -> list[Lesson] | None:
        return None

    async def set(
        self,
        *,
        class_id: int,
        day: date,
        lessons: list[Lesson],
        ttl_seconds: int,
    ) -> None:
        return None

    async def aclose(self) -> None:
        return None


@pytest.fixture
def unused_uow_factory() -> UnitOfWorkFactory:
    def factory() -> Never:
        raise AssertionError("This test must not create a UnitOfWork")

    return factory
