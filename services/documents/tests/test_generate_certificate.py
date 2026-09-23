from datetime import UTC, datetime
from typing import Self
from uuid import UUID, uuid4

from document_service.application.generate_certificate import (
    GenerateCertificateCommand,
    GenerateCertificateHandler,
)
from document_service.domain.certificate import CertificateData
from document_service.domain.document import DocumentJob, DocumentStatus


class FakeDocumentRepository:
    def __init__(self, job: DocumentJob | None) -> None:
        self._job = job
        self.processing_job_ids: list[UUID] = []
        self.completed_jobs: list[tuple[UUID, str]] = []

    def get_job(self, job_id: UUID) -> DocumentJob | None:
        if self._job is not None and self._job.id == job_id:
            return self._job
        return None

    def mark_processing(self, job_id: UUID) -> None:
        self.processing_job_ids.append(job_id)

    def mark_completed(self, job_id: UUID, object_key: str) -> None:
        self.completed_jobs.append((job_id, object_key))


class FakeUnitOfWork:
    def __init__(self, repository: FakeDocumentRepository) -> None:
        self.documents = repository

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        return None


class FakeCertificateRenderer:
    def __init__(self) -> None:
        self.rendered_certificates: list[CertificateData] = []

    def render(self, certificate: CertificateData) -> bytes:
        self.rendered_certificates.append(certificate)
        return b"%PDF-1.7\ncertificate"


class FakeDocumentStorage:
    def __init__(self) -> None:
        self.uploaded_pdfs: list[tuple[str, bytes]] = []

    def read(self, object_key: str) -> bytes:
        raise AssertionError("read is not used while generating a certificate")

    def put_pdf(self, object_key: str, pdf_bytes: bytes) -> None:
        self.uploaded_pdfs.append((object_key, pdf_bytes))


def make_pending_job() -> DocumentJob:
    return DocumentJob(
        id=uuid4(),
        document_type="certificate",
        status=DocumentStatus.PENDING,
        payload={
            "student_full_name": "Иван Петров",
            "class_name": "7А",
            "academic_year": "2026/2027",
        },
        object_key=None,
        error_message=None,
        created_at=datetime(2026, 9, 22, tzinfo=UTC),
    )


def test_handler_generates_certificate_and_marks_job_completed() -> None:
    job = make_pending_job()
    repository = FakeDocumentRepository(job)
    renderer = FakeCertificateRenderer()
    storage = FakeDocumentStorage()
    handler = GenerateCertificateHandler(
        uow_factory=lambda: FakeUnitOfWork(repository),
        renderer=renderer,
        storage=storage,
    )

    handler.handle(GenerateCertificateCommand(job_id=job.id))

    object_key = f"certificates/{job.id}.pdf"
    assert repository.processing_job_ids == [job.id]
    assert renderer.rendered_certificates == [
        CertificateData("Иван Петров", "7А", "2026/2027")
    ]
    assert storage.uploaded_pdfs == [(object_key, b"%PDF-1.7\ncertificate")]
    assert repository.completed_jobs == [(job.id, object_key)]


def test_handler_skips_already_completed_job() -> None:
    job = make_pending_job()
    job = DocumentJob(
        id=job.id,
        document_type=job.document_type,
        status=DocumentStatus.COMPLETED,
        payload=job.payload,
        object_key=f"certificates/{job.id}.pdf",
        error_message=None,
        created_at=job.created_at,
    )
    repository = FakeDocumentRepository(job)
    renderer = FakeCertificateRenderer()
    storage = FakeDocumentStorage()
    handler = GenerateCertificateHandler(
        uow_factory=lambda: FakeUnitOfWork(repository),
        renderer=renderer,
        storage=storage,
    )

    handler.handle(GenerateCertificateCommand(job_id=job.id))

    assert repository.processing_job_ids == []
    assert renderer.rendered_certificates == []
    assert storage.uploaded_pdfs == []
    assert repository.completed_jobs == []
