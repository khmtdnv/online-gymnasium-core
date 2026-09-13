from sqlalchemy.ext.asyncio import AsyncSession

from schedule_service.domain.events import LessonCreated
from schedule_service.infrastructure.models.outbox_event import OutboxEventRow


class SqlAlchemyOutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: LessonCreated) -> None:
        row = OutboxEventRow(
            event_type="lesson.created",
            payload={
                "id": event.lesson_id,
                "class_id": event.class_id,
                "teacher_id": event.teacher_id,
                "subject_id": event.subject_id,
                "starts_at": event.starts_at.isoformat(),
                "ends_at": event.ends_at.isoformat(),
                "status": event.status,
                "version": event.version,
            },
        )
        self._session.add(row)
