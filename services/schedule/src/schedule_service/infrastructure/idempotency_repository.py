from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from schedule_service.application.ports.idempotency_repository import IdempotencyRecord
from schedule_service.domain.lesson import Lesson
from schedule_service.infrastructure.models.idempotency_request import IdempotencyRequestRow
from schedule_service.infrastructure.models.scheduled_lesson import ScheduledLessonRow


class SqlAlchemyIdempotencyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim(self, operation: str, key: str, request_hash: str) -> IdempotencyRecord | None:
        statement = (
            insert(IdempotencyRequestRow)
            .values(
                operation=operation,
                idempotency_key=key,
                request_hash=request_hash,
            )
            .on_conflict_do_nothing(
                constraint="idempotency_requests_operation_key_unique",
            )
            .returning(IdempotencyRequestRow.id)
        )

        claimed_id = await self._session.scalar(statement)

        if claimed_id is not None:
            return None

        statement = select(IdempotencyRequestRow).where(
            IdempotencyRequestRow.operation == operation,
            IdempotencyRequestRow.idempotency_key == key,
        )
        existing_record = await self._session.scalar(statement)
        assert existing_record is not None

        if existing_record.lesson_id is None:
            return IdempotencyRecord(
                request_hash=existing_record.request_hash,
                lesson=None,
            )

        statement = select(ScheduledLessonRow).where(ScheduledLessonRow.id == existing_record.lesson_id)
        orm_lesson = await self._session.scalar(statement)
        assert orm_lesson is not None

        return IdempotencyRecord(
            request_hash=existing_record.request_hash,
            lesson=Lesson(
                id=orm_lesson.id,
                class_id=orm_lesson.class_id,
                teacher_id=orm_lesson.teacher_id,
                subject_id=orm_lesson.subject_id,
                starts_at=orm_lesson.starts_at,
                ends_at=orm_lesson.ends_at,
                status=orm_lesson.status,
                version=orm_lesson.version,
            ),
        )

    async def complete(self, operation: str, key: str, lesson: Lesson) -> None:
        assert lesson.id is not None
        statement = (
            update(IdempotencyRequestRow)
            .where(
                IdempotencyRequestRow.operation == operation,
                IdempotencyRequestRow.idempotency_key == key,
            )
            .values(lesson_id=lesson.id)
        )
        await self._session.execute(statement)
