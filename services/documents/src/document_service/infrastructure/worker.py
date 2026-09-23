from pathlib import Path

from celery import Celery
from minio import Minio

from document_service.application.generate_certificate import (
    GenerateCertificateHandler,
)
from document_service.config import DocumentSettings
from document_service.infrastructure.celery_app import create_celery_app
from document_service.infrastructure.celery_tasks import register_certificate_tasks
from document_service.infrastructure.database import create_engine, session_factory
from document_service.infrastructure.minio_storage import MinioDocumentStorage
from document_service.infrastructure.renderer import create_certificate_renderer
from document_service.infrastructure.uow import SqlAlchemyDocumentUnitOfWork


def create_worker_app(settings: DocumentSettings) -> Celery:
    engine = create_engine(settings.document_database_url)
    sessions = session_factory(engine)

    storage = MinioDocumentStorage(
        client=Minio(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        ),
        bucket=settings.minio_bucket,
    )
    renderer = create_certificate_renderer(
        Path(__file__).resolve().parents[3] / "templates",
    )

    handler = GenerateCertificateHandler(
        uow_factory=lambda: SqlAlchemyDocumentUnitOfWork(sessions),
        renderer=renderer,
        storage=storage,
    )

    celery_app = create_celery_app(settings)
    register_certificate_tasks(celery_app=celery_app, handler_factory=lambda: handler)
    return celery_app


celery_app = create_worker_app(DocumentSettings())
