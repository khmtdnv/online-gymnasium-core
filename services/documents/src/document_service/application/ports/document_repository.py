from typing import Protocol
from uuid import UUID

from document_service.domain.certificate import CertificateData
from document_service.domain.document import DocumentJob


class DocumentRepository(Protocol):
    def create_job_with_outbox(self, certificate: CertificateData) -> DocumentJob: ...

    def get_job(self, job_id: UUID) -> DocumentJob | None: ...

    def mark_processing(self, job_id: UUID) -> None: ...

    def mark_completed(self, job_id: UUID, object_key: str) -> None: ...

    def mark_failed(self, job_id: UUID, error_message: str) -> None: ...
