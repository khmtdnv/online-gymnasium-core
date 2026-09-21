from uuid import uuid4

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

        return DocumentJob(
            id=job_row.id,
            document_type=job_row.document_type,
            status=DocumentStatus(job_row.status),
            object_key=job_row.object_key,
            error_message=job_row.error_message,
            created_at=job_row.created_at,
        )
