from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select, update
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
            id=row.id,
            class_id=row.class_id,
            teacher_id=row.teacher_id,
            subject_id=row.subject_id,
            starts_at=row.starts_at,
            ends_at=row.ends_at,
            status=row.status,
            version=row.version,
        )

    async def get(self, lesson_id: int) -> Lesson | None:
        statement = select(ScheduledLessonRow).where(ScheduledLessonRow.id == lesson_id)
        scalar_result = await self._session.scalars(statement)
        row = scalar_result.one_or_none()

        if row is None:
            return None

        return Lesson(
            id=row.id,
            class_id=row.class_id,
            teacher_id=row.teacher_id,
            subject_id=row.subject_id,
            starts_at=row.starts_at,
            ends_at=row.ends_at,
            status=row.status,
            version=row.version,
        )

    async def update(self, lesson: Lesson, expected_version: int) -> Lesson | None:
        statement = (
            update(ScheduledLessonRow)
            .where(
                ScheduledLessonRow.id == lesson.id,
                ScheduledLessonRow.version == expected_version,
            )
            .values(
                starts_at=lesson.starts_at,
                ends_at=lesson.ends_at,
                version=ScheduledLessonRow.version + 1,
            )
            .returning(ScheduledLessonRow)
        )

        try:
            scalar_result = await self._session.scalars(statement)
        except IntegrityError as exc:
            raise ScheduleConflict from exc

        row = scalar_result.one_or_none()

        if row is None:
            return None

        return Lesson(
            id=row.id,
            class_id=row.class_id,
            teacher_id=row.teacher_id,
            subject_id=row.subject_id,
            starts_at=row.starts_at,
            ends_at=row.ends_at,
            status=row.status,
            version=row.version,
        )

    async def cancel(self, lesson: Lesson, expected_version: int) -> Lesson | None:
        statement = (
            update(ScheduledLessonRow)
            .where(
                ScheduledLessonRow.id == lesson.id,
                ScheduledLessonRow.version == expected_version,
                ScheduledLessonRow.status == "planned",
            )
            .values(
                status=lesson.status,
                version=ScheduledLessonRow.version + 1,
            )
            .returning(ScheduledLessonRow)
        )

        scalar_result = await self._session.scalars(statement)
        row = scalar_result.one_or_none()

        if row is None:
            return None

        return Lesson(
            id=row.id,
            class_id=row.class_id,
            teacher_id=row.teacher_id,
            subject_id=row.subject_id,
            starts_at=row.starts_at,
            ends_at=row.ends_at,
            status=row.status,
            version=row.version,
        )

    async def get_class_schedule(self, *, class_id: int, day: date) -> list[Lesson]:
        day_start = datetime.combine(day, time.min, tzinfo=UTC)
        day_end = day_start + timedelta(days=1)

        statement = (
            select(ScheduledLessonRow)
            .where(
                ScheduledLessonRow.class_id == class_id,
                ScheduledLessonRow.status == "planned",
                ScheduledLessonRow.starts_at < day_end,
                ScheduledLessonRow.ends_at > day_start,
            )
            .order_by(ScheduledLessonRow.starts_at)
        )
        orm_lessons = (await self._session.scalars(statement)).all()

        domain_lessons = []
        for lesson in orm_lessons:
            domain_lessons.append(
                Lesson(
                    id=lesson.id,
                    class_id=lesson.class_id,
                    teacher_id=lesson.teacher_id,
                    subject_id=lesson.subject_id,
                    starts_at=lesson.starts_at,
                    ends_at=lesson.ends_at,
                    status=lesson.status,
                    version=lesson.version,
                )
            )

        return domain_lessons
