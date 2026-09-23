from datetime import UTC, datetime
from typing import Self
from uuid import UUID, uuid4

import pytest


def test_handler_creates_pending_job_and_matching_outbox_row() -> None:
    from document_service.application.create_certificate import (
        CreateCertificateCommand,
        CreateCertificateHandler,
    )
    from document_service.domain.certificate import CertificateData
    from document_service.domain.document import DocumentJob, DocumentStatus

    class FakeDocumentRepository:
        def __init__(self) -> None:
            self.jobs: list[DocumentJob] = []
            self.outbox_document_job_ids: list[UUID] = []

        def create_job_with_outbox(self, certificate: CertificateData) -> DocumentJob:
            job = DocumentJob(
                id=uuid4(),
                document_type="certificate",
                status=DocumentStatus.PENDING,
                payload={
                    "student_full_name": certificate.student_full_name,
                    "class_name": certificate.class_name,
                    "academic_year": certificate.academic_year,
                },
                object_key=None,
                error_message=None,
                created_at=datetime(2026, 9, 21, tzinfo=UTC),
            )
            self.jobs.append(job)
            self.outbox_document_job_ids.append(job.id)
            return job

    class FakeDocumentUnitOfWork:
        def __init__(self) -> None:
            self.documents = FakeDocumentRepository()
            self.was_entered = False

        def __enter__(self) -> Self:
            self.was_entered = True
            return self

        def __exit__(
            self,
            exc_type: object,
            exc: object,
            traceback: object,
        ) -> None:
            return None

    fake_uow = FakeDocumentUnitOfWork()
    handler = CreateCertificateHandler(uow_factory=lambda: fake_uow)

    result = handler.handle(
        CreateCertificateCommand(
            student_full_name="Иван Петров",
            class_name="7А",
            academic_year="2026/2027",
        )
    )

    assert result.status is DocumentStatus.PENDING
    assert fake_uow.was_entered is True
    assert fake_uow.documents.jobs[0].document_type == "certificate"
    assert fake_uow.documents.outbox_document_job_ids == [result.id]


def test_certificate_data_rejects_blank_student_name() -> None:
    from document_service.domain.certificate import (
        CertificateData,
        InvalidCertificateData,
    )

    with pytest.raises(InvalidCertificateData):
        CertificateData(
            student_full_name=" ",
            class_name="7А",
            academic_year="2026/2027",
        )
