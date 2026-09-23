from document_service.config import DocumentSettings


def test_create_runtime_app_wires_postgres_uow_and_minio_storage(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "DOCUMENT_DATABASE_URL",
        "postgresql+psycopg://documents:documents@localhost/documents",
    )
    monkeypatch.setenv(
        "CELERY_BROKER_URL", "amqp://documents:documents@localhost:5672//"
    )
    monkeypatch.setenv("MINIO_ENDPOINT", "localhost:9000")
    from document_service.infrastructure.minio_storage import MinioDocumentStorage
    from document_service.infrastructure.unit_of_work import (
        SqlAlchemyDocumentUnitOfWork,
    )
    from document_service.main import create_runtime_app

    settings = DocumentSettings(
        document_database_url="postgresql+psycopg://documents:documents@localhost/documents",
        celery_broker_url="amqp://documents:documents@localhost:5672//",
        minio_endpoint="localhost:9000",
        minio_access_key="documents",
        minio_secret_key="documents-password",
        minio_bucket="documents",
    )

    app = create_runtime_app(settings)

    assert app.title == "Document Service"
    assert app.state.settings is settings
    assert isinstance(app.state.storage, MinioDocumentStorage)
    assert isinstance(app.state.uow_factory(), SqlAlchemyDocumentUnitOfWork)
