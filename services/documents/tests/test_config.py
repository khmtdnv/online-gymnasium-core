def test_settings_read_document_urls_from_environment(monkeypatch) -> None:
    from document_service.config import DocumentSettings

    monkeypatch.setenv(
        "DOCUMENT_DATABASE_URL",
        "postgresql+psycopg://documents:password@documents-postgres/documents",
    )
    monkeypatch.setenv(
        "CELERY_BROKER_URL",
        "amqp://guest:guest@rabbitmq:5672//",
    )
    monkeypatch.setenv("MINIO_ENDPOINT", "minio:9000")

    settings = DocumentSettings()

    assert settings.document_database_url.endswith("/documents")
    assert settings.celery_broker_url.endswith("//")
    assert settings.minio_bucket == "documents"
