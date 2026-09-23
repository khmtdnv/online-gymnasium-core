from minio import Minio

from document_service.app import create_app
from document_service.config import DocumentSettings
from document_service.infrastructure.database import create_engine, session_factory
from document_service.infrastructure.minio_storage import MinioDocumentStorage
from document_service.infrastructure.uow import SqlAlchemyDocumentUnitOfWork


def create_runtime_app(settings: DocumentSettings):
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
    return create_app(
        settings=settings,
        uow_factory=lambda: SqlAlchemyDocumentUnitOfWork(sessions),
        storage=storage,
    )


app = create_runtime_app(DocumentSettings())
