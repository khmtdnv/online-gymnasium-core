from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from document_service.application.ports.document_task_outbox_repository import (
    PendingDocumentTask,
)
from document_service.infrastructure.models.document_task_outbox import (
    DocumentTaskOutboxRow,
)


class SqlAlchemyDocumentTaskOutboxRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_pending(self, *, limit: int) -> list[PendingDocumentTask]:
        statement = (
            select(DocumentTaskOutboxRow)
            .where(DocumentTaskOutboxRow.published_at.is_(None))
            .order_by(DocumentTaskOutboxRow.created_at)
            .limit(limit)
        )
        rows = self._session.scalars(statement).all()

        return [
            PendingDocumentTask(
                id=row.id,
                document_job_id=row.document_job_id,
                task_name=row.task_name,
                created_at=row.created_at,
            )
            for row in rows
        ]

    def mark_published(self, *, task_id: UUID) -> None:
        statement = (
            update(DocumentTaskOutboxRow)
            .where(
                DocumentTaskOutboxRow.id == task_id,
                DocumentTaskOutboxRow.published_at.is_(None),
            )
            .values(published_at=func.now())
        )
        self._session.execute(statement)
