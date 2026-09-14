from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from schedule_service.application.ports.outbox_repository import PendingOutboxEvent
from schedule_service.domain.events import LessonCreated, ScheduleChanged
from schedule_service.infrastructure.models.outbox_event import OutboxEventRow


class SqlAlchemyOutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: LessonCreated | ScheduleChanged) -> None:
        if isinstance(event, LessonCreated):
            row = OutboxEventRow(
                event_type="lesson.created",
                payload={
                    "lesson_id": event.lesson_id,
                    "class_id": event.class_id,
                    "teacher_id": event.teacher_id,
                    "subject_id": event.subject_id,
                    "starts_at": event.starts_at.isoformat(),
                    "ends_at": event.ends_at.isoformat(),
                    "status": event.status,
                    "version": event.version,
                },
            )
        elif isinstance(event, ScheduleChanged):
            row = OutboxEventRow(
                event_type="schedule.changed",
                payload={
                    "lesson_id": event.lesson_id,
                    "class_id": event.class_id,
                    "affected_dates": [day.isoformat() for day in event.affected_dates],
                },
            )
        else:
            raise TypeError(f"Unsupported outbox event: {type(event).__name__}")

        self._session.add(row)

    async def get_pending(self, *, limit: int) -> list[PendingOutboxEvent]:
        statement = (
            select(OutboxEventRow)
            .where(OutboxEventRow.published_at.is_(None))
            .order_by(OutboxEventRow.id)
            .limit(limit)
        )

        rows = (await self._session.scalars(statement)).all()
        result_list: list[PendingOutboxEvent] = []

        for row in rows:
            payload = dict(row.payload)
            if "lesson_id" not in payload and "id" in payload:
                payload["lesson_id"] = payload.pop("id")

            result_list.append(
                PendingOutboxEvent(
                    id=row.id,
                    event_type=row.event_type,
                    payload=payload,
                    created_at=row.created_at,
                )
            )

        return result_list

    async def mark_published(self, *, event_id: int) -> None:
        statement = (
            update(OutboxEventRow)
            .where(
                OutboxEventRow.id == event_id,
                OutboxEventRow.published_at.is_(None),
            )
            .values(published_at=func.now())
        )
        await self._session.execute(statement)
