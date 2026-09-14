from datetime import date
from typing import Protocol

from schedule_service.domain.lesson import Lesson


class ScheduleCache(Protocol):
    async def get(self, *, class_id: int, day: date) -> list[Lesson] | None: ...
    async def get_generation(self, *, class_id: int, day: date) -> int: ...
    async def try_acquire_fill_lock(
        self,
        *,
        class_id: int,
        day: date,
        token: str,
        ttl_ms: int,
    ) -> bool: ...
    async def release_fill_lock(
        self,
        *,
        class_id: int,
        day: date,
        token: str,
    ) -> None: ...
    async def set_if_generation(
        self,
        *,
        class_id: int,
        day: date,
        lessons: list[Lesson],
        ttl_seconds: int,
        expected_generation: int,
    ) -> bool: ...
    async def invalidate(self, *, class_id: int, days: tuple[date, ...]) -> None: ...
    async def aclose(self) -> None: ...
