from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from document_service.domain.certificate import CertificateData
from document_service.domain.document import DocumentJob, DocumentStatus
from document_service.infrastructure.models.document_job import DocumentJobRow
from document_service.infrastructure.models.document_task_outbox import (
    DocumentTaskOutboxRow,
)


class SqlAlchemyDocumentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_job_with_outbox(self, certificate: CertificateData) -> DocumentJob:
        job_id = uuid4()
        job_row = DocumentJobRow(
            id=job_id,
            document_type="certificate",
            status=DocumentStatus.PENDING.value,
            payload={
                "student_full_name": certificate.student_full_name,
                "class_name": certificate.class_name,
                "academic_year": certificate.academic_year,
            },
        )
        outbox_row = DocumentTaskOutboxRow(
            id=uuid4(),
            document_job_id=job_id,
            task_name="documents.generate_certificate",
        )
        self._session.add_all([job_row, outbox_row])
        self._session.flush()
        self._session.refresh(job_row)

        return self._to_document_job(job_row)

    def get_job(self, job_id: UUID) -> DocumentJob | None:
        statement = select(DocumentJobRow).where(DocumentJobRow.id == job_id)
        row = self._session.scalar(statement)

        if row is None:
            return None

        return self._to_document_job(row)

    def mark_processing(self, job_id: UUID) -> None:
        statement = (
            update(DocumentJobRow)
            .where(DocumentJobRow.id == job_id)
            .values(status=DocumentStatus.PROCESSING.value)
        )
        self._session.execute(statement)

    def mark_completed(self, job_id: UUID, object_key: str) -> None:
        statement = (
            update(DocumentJobRow)
            .where(DocumentJobRow.id == job_id)
            .values(status=DocumentStatus.COMPLETED.value, object_key=object_key)
        )
        self._session.execute(statement)

    @staticmethod
    def _to_document_job(row: DocumentJobRow) -> DocumentJob:
        return DocumentJob(
            id=row.id,
            document_type=row.document_type,
            status=DocumentStatus(row.status),
            payload=row.payload,
            object_key=row.object_key,
            error_message=row.error_message,
            created_at=row.created_at,
        )
