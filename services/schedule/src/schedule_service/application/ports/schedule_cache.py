from datetime import date
from typing import Protocol

from schedule_service.domain.lesson import Lesson


class ScheduleCache(Protocol):
    async def get(self, *, class_id: int, day: date) -> list[Lesson] | None: ...
    async def set(
        self,
        *,
        class_id: int,
        day: date,
        lessons: list[Lesson],
        ttl_seconds: int,
    ) -> None: ...
    async def aclose(self) -> None: ...
    async def invalidate(self, *, class_id: int, days: tuple[date, ...]) -> None: ...
