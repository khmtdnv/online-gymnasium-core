from dataclasses import dataclass
from datetime import date

from schedule_service.application.ports.schedule_cache import ScheduleCache
from schedule_service.application.ports.unit_of_work import UnitOfWorkFactory
from schedule_service.domain.lesson import Lesson


@dataclass(frozen=True, slots=True)
class ListLessonsQuery:
    class_id: int
    day: date


class ListLessonsHandler:
    def __init__(self, uow_factory: UnitOfWorkFactory, cache: ScheduleCache):
        self._uow_factory = uow_factory
        self._cache = cache

    async def handle(self, query: ListLessonsQuery) -> list[Lesson]:
        cached_lessons = await self._cache.get(class_id=query.class_id, day=query.day)
        if cached_lessons is not None:
            return cached_lessons

        async with self._uow_factory() as uow:
            lessons = await uow.lessons.list_planned_for_class_on_day(
                class_id=query.class_id,
                day=query.day,
            )

        await self._cache.set(
            class_id=query.class_id,
            day=query.day,
            lessons=lessons,
            ttl_seconds=60,
        )

        return lessons
