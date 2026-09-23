from datetime import UTC, datetime
from typing import Self
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from document_service.config import DocumentSettings
from document_service.domain.certificate import CertificateData
from document_service.domain.document import DocumentJob, DocumentStatus


class FakeDocumentRepository:
    def __init__(self) -> None:
        self.jobs: dict[UUID, DocumentJob] = {}

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
            created_at=datetime(2026, 9, 22, tzinfo=UTC),
        )
        self.jobs[job.id] = job
        return job

    def get_job(self, job_id: UUID) -> DocumentJob | None:
        return self.jobs.get(job_id)


class FakeDocumentUnitOfWork:
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


class FakeDocumentStorage:
    def __init__(self, content: bytes = b"%PDF-1.7\n") -> None:
        self._content = content

    def read(self, object_key: str) -> bytes:
        return self._content


def create_test_app(
    repository: FakeDocumentRepository | None = None,
    storage: FakeDocumentStorage | None = None,
):
    from document_service.app import create_app

    settings = DocumentSettings(
        document_database_url="postgresql+psycopg://documents:documents@localhost/documents",
        celery_broker_url="amqp://documents:documents@localhost:5672//",
        minio_endpoint="localhost:9000",
    )
    document_repository = repository or FakeDocumentRepository()
    document_storage = storage or FakeDocumentStorage()
    return create_app(
        settings=settings,
        uow_factory=lambda: FakeDocumentUnitOfWork(document_repository),
        storage=document_storage,
    )


def test_post_certificate_returns_pending_job() -> None:
    with TestClient(create_test_app()) as client:
        response = client.post(
            "/documents/certificates",
            json={
                "student_full_name": "Иван Петров",
                "class_name": "7А",
                "academic_year": "2026/2027",
            },
        )

    assert response.status_code == 202
    assert response.json()["document_type"] == "certificate"
    assert response.json()["status"] == "pending"


def test_post_certificate_returns_422_for_blank_student_name() -> None:
    with TestClient(create_test_app(), raise_server_exceptions=False) as client:
        response = client.post(
            "/documents/certificates",
            json={
                "student_full_name": " ",
                "class_name": "7А",
                "academic_year": "2026/2027",
            },
        )

    assert response.status_code == 422


def test_get_document_returns_completed_job_with_download_url() -> None:
    job = DocumentJob(
        id=uuid4(),
        document_type="certificate",
        status=DocumentStatus.COMPLETED,
        payload={},
        object_key="certificates/example.pdf",
        error_message=None,
        created_at=datetime(2026, 9, 22, tzinfo=UTC),
    )
    repository = FakeDocumentRepository()
    repository.jobs[job.id] = job

    with TestClient(create_test_app(repository)) as client:
        response = client.get(f"/documents/{job.id}")

    assert response.status_code == 200
    assert response.json() == {
        "id": str(job.id),
        "document_type": "certificate",
        "status": "completed",
        "created_at": "2026-09-22T00:00:00Z",
        "download_url": f"/documents/{job.id}/content",
    }


def test_get_document_returns_404_when_job_does_not_exist() -> None:
    with TestClient(create_test_app()) as client:
        response = client.get(f"/documents/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Document was not found"}


def test_get_document_omits_download_url_until_completion() -> None:
    job = DocumentJob(
        id=uuid4(),
        document_type="certificate",
        status=DocumentStatus.PENDING,
        payload={},
        object_key=None,
        error_message=None,
        created_at=datetime(2026, 9, 22, tzinfo=UTC),
    )
    repository = FakeDocumentRepository()
    repository.jobs[job.id] = job

    with TestClient(create_test_app(repository)) as client:
        response = client.get(f"/documents/{job.id}")

    assert response.status_code == 200
    assert "download_url" not in response.json()


@pytest.mark.parametrize(
    "document_status",
    [DocumentStatus.PENDING, DocumentStatus.PROCESSING],
)
def test_content_returns_409_until_document_is_completed(
    document_status: DocumentStatus,
) -> None:
    job = DocumentJob(
        id=uuid4(),
        document_type="certificate",
        status=document_status,
        payload={},
        object_key=None,
        error_message=None,
        created_at=datetime(2026, 9, 22, tzinfo=UTC),
    )
    repository = FakeDocumentRepository()
    repository.jobs[job.id] = job

    with TestClient(create_test_app(repository)) as client:
        response = client.get(f"/documents/{job.id}/content")

    assert response.status_code == 409
    assert response.json() == {"detail": "Document is not ready"}


def test_content_returns_409_for_failed_job() -> None:
    job = DocumentJob(
        id=uuid4(),
        document_type="certificate",
        status=DocumentStatus.FAILED,
        payload={},
        object_key=None,
        error_message="Rendering failed",
        created_at=datetime(2026, 9, 22, tzinfo=UTC),
    )
    repository = FakeDocumentRepository()
    repository.jobs[job.id] = job

    with TestClient(create_test_app(repository)) as client:
        response = client.get(f"/documents/{job.id}/content")

    assert response.status_code == 409
    assert response.json() == {"detail": "Document generation failed"}


def test_content_returns_pdf_for_completed_job() -> None:
    job = DocumentJob(
        id=uuid4(),
        document_type="certificate",
        status=DocumentStatus.COMPLETED,
        payload={},
        object_key="certificates/example.pdf",
        error_message=None,
        created_at=datetime(2026, 9, 22, tzinfo=UTC),
    )
    repository = FakeDocumentRepository()
    repository.jobs[job.id] = job
    content = b"%PDF-1.7\nexample"

    with TestClient(
        create_test_app(repository, FakeDocumentStorage(content))
    ) as client:
        response = client.get(f"/documents/{job.id}/content")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == content
