from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from document_service.domain.certificate import CertificateData
    from document_service.domain.document import DocumentJob


class DocumentRepository(Protocol):
    def create_job_with_outbox(self, certificate: CertificateData) -> DocumentJob: ...
