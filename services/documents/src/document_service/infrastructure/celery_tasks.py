from collections.abc import Callable
from uuid import UUID

from celery import Celery

from document_service.application.generate_certificate import (
    GenerateCertificateCommand,
    GenerateCertificateHandler,
)


def register_certificate_tasks(
    celery_app: Celery,
    handler_factory: Callable[[], GenerateCertificateHandler],
) -> None:
    @celery_app.task(name="documents.generate_certificate", ignore_result=True)
    def generate_certificate(job_id: str) -> None:
        handler = handler_factory()
        handler.handle(GenerateCertificateCommand(job_id=UUID(job_id)))
