from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from schedule_service.application.errors import ScheduleConflict
from schedule_service.domain.lesson import Lesson
from schedule_service.infrastructure.models.scheduled_lesson import ScheduledLessonRow


class SqlAlchemyLessonRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, lesson: Lesson) -> Lesson:
        row = ScheduledLessonRow(
            class_id=lesson.class_id,
            teacher_id=lesson.teacher_id,
            subject_id=lesson.subject_id,
            starts_at=lesson.starts_at,
            ends_at=lesson.ends_at,
        )

        self._session.add(row)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise ScheduleConflict from exc
        await self._session.refresh(row)

        return Lesson(
            class_id=row.class_id,
            teacher_id=row.teacher_id,
            subject_id=row.subject_id,
            starts_at=row.starts_at,
            ends_at=row.ends_at,
            id=row.id,
            status=row.status,
            version=row.version,
        )
