import importlib
import sys


def test_worker_module_builds_celery_app_with_certificate_task(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "DOCUMENT_DATABASE_URL",
        "sqlite://",
    )
    monkeypatch.setenv("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//")
    monkeypatch.setenv("MINIO_ENDPOINT", "localhost:9000")
    sys.modules.pop("document_service.infrastructure.worker", None)

    worker = importlib.import_module("document_service.infrastructure.worker")

    assert "documents.generate_certificate" in worker.celery_app.tasks
