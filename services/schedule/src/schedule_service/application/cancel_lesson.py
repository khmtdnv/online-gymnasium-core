from dataclasses import dataclass

from schedule_service.application.errors import LessonNotFound, VersionConflict
from schedule_service.application.ports.unit_of_work import UnitOfWorkFactory
from schedule_service.domain.events import ScheduleChanged
from schedule_service.domain.lesson import Lesson


@dataclass(frozen=True, slots=True)
class CancelLessonCommand:
    lesson_id: int
    expected_version: int


class CancelLessonHandler:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def handle(self, command: CancelLessonCommand) -> Lesson:
        async with self._uow_factory() as uow:
            lesson = await uow.lessons.get(lesson_id=command.lesson_id)

            if lesson is None:
                raise LessonNotFound

            lesson.cancel()

            canceled_lesson = await uow.lessons.cancel(
                lesson=lesson, expected_version=command.expected_version
            )
            if canceled_lesson is None:
                raise VersionConflict

            assert canceled_lesson.id is not None
            await uow.outbox.add(
                ScheduleChanged(
                    lesson_id=canceled_lesson.id,
                    class_id=canceled_lesson.class_id,
                    affected_dates=(canceled_lesson.starts_at.date(),),
                )
            )

            return canceled_lesson
