from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Self

from schedule_service.domain.lesson import Lesson


@dataclass(frozen=True, slots=True)
class CreateLessonCommand:
    class_id: int
    teacher_id: int
    subject_id: int
    starts_at: datetime
    ends_at: datetime


class LessonRepository(Protocol):
    async def add(self, lesson: Lesson) -> Lesson: ...


class UnitOfWork(Protocol):
    lessons: LessonRepository

    async def __aenter__(self) -> Self: ...

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None: ...


type UnitOfWorkFactory = Callable[[], UnitOfWork]


class CreateLessonHandler:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def handle(self, command: CreateLessonCommand) -> Lesson:
        lesson = Lesson.create(
            class_id=command.class_id,
            teacher_id=command.teacher_id,
            subject_id=command.subject_id,
            starts_at=command.starts_at,
            ends_at=command.ends_at,
        )

        async with self._uow_factory() as uow:
            return await uow.lessons.add(lesson)
