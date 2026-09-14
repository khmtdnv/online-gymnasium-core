from dataclasses import dataclass
from datetime import date

from schedule_service.application.ports.unit_of_work import UnitOfWorkFactory
from schedule_service.domain.lesson import Lesson


@dataclass(frozen=True, slots=True)
class ListLessonsQuery:
    class_id: int
    day: date


class ListLessonsHandler:
    def __init__(self, uow_factory: UnitOfWorkFactory):
        self._uow_factory = uow_factory

    async def handle(self, query: ListLessonsQuery) -> list[Lesson]:
        async with self._uow_factory() as uow:
            return await uow.lessons.list_planned_for_class_on_day(class_id=query.class_id, day=query.day)
