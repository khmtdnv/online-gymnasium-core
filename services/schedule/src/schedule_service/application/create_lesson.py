from dataclasses import dataclass
from datetime import datetime

from schedule_service.application.errors import IdempotencyKeyReuse
from schedule_service.application.ports.unit_of_work import UnitOfWorkFactory
from schedule_service.domain.events import LessonCreated
from schedule_service.domain.lesson import Lesson


@dataclass(frozen=True, slots=True)
class CreateLessonCommand:
    class_id: int
    teacher_id: int
    subject_id: int
    starts_at: datetime
    ends_at: datetime
    idempotency_key: str | None = None
    request_hash: str | None = None


class CreateLessonHandler:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def handle(self, command: CreateLessonCommand) -> Lesson:
        async with self._uow_factory() as uow:
            if command.idempotency_key is not None:
                assert command.request_hash is not None

                record = await uow.idempotency.claim(
                    "create_lesson", command.idempotency_key, command.request_hash
                )

                if record is not None:
                    if record.request_hash != command.request_hash:
                        raise IdempotencyKeyReuse

                    assert record.lesson is not None
                    return record.lesson

            lesson = Lesson.create(
                class_id=command.class_id,
                teacher_id=command.teacher_id,
                subject_id=command.subject_id,
                starts_at=command.starts_at,
                ends_at=command.ends_at,
            )

            db_lesson = await uow.lessons.add(lesson)

            assert db_lesson.id is not None
            lesson_created = LessonCreated(
                lesson_id=db_lesson.id,
                class_id=db_lesson.class_id,
                teacher_id=db_lesson.teacher_id,
                subject_id=db_lesson.subject_id,
                starts_at=db_lesson.starts_at,
                ends_at=db_lesson.ends_at,
                status=db_lesson.status,
                version=db_lesson.version,
            )
            await uow.outbox.add(lesson_created)

            if command.idempotency_key is not None:
                assert command.request_hash is not None
                await uow.idempotency.complete(
                    "create_lesson", command.idempotency_key, db_lesson
                )

            return db_lesson
