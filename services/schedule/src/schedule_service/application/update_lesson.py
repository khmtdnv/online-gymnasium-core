from dataclasses import dataclass
from datetime import datetime

from schedule_service.application.errors import LessonNotFound, VersionConflict
from schedule_service.application.ports.unit_of_work import UnitOfWorkFactory
from schedule_service.domain.events import ScheduleChanged
from schedule_service.domain.lesson import Lesson


@dataclass(frozen=True, slots=True)
class UpdateLessonCommand:
    lesson_id: int
    starts_at: datetime
    ends_at: datetime
    expected_version: int


class UpdateLessonHandler:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def handle(self, command: UpdateLessonCommand) -> Lesson:
        async with self._uow_factory() as uow:
            lesson = await uow.lessons.get(lesson_id=command.lesson_id)

            if lesson is None:
                raise LessonNotFound

            old_day = lesson.starts_at.date()

            lesson.reschedule(starts_at=command.starts_at, ends_at=command.ends_at)

            updated_lesson = await uow.lessons.update(
                lesson=lesson,
                expected_version=command.expected_version,
            )

            if updated_lesson is None:
                raise VersionConflict

            assert updated_lesson.id is not None
            await uow.outbox.add(
                ScheduleChanged(
                    lesson_id=updated_lesson.id,
                    class_id=updated_lesson.class_id,
                    affected_dates=tuple(
                        sorted({old_day, updated_lesson.starts_at.date()})
                    ),
                )
            )

            return updated_lesson
