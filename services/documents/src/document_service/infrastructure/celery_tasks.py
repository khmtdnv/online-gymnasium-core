from collections.abc import Callable
from uuid import UUID

from celery import Celery

from document_service.application.errors import (
    PermanentDocumentError,
    TemporaryStorageError,
)
from document_service.application.generate_certificate import (
    GenerateCertificateCommand,
    GenerateCertificateHandler,
)
from document_service.application.mark_job_failed import (
    MarkJobFailedCommand,
    MarkJobFailedHandler,
)


def register_certificate_tasks(
    celery_app: Celery,
    handler_factory: Callable[[], GenerateCertificateHandler],
    failure_handler_factory: Callable[[], MarkJobFailedHandler],
) -> None:
    @celery_app.task(
        name="documents.generate_certificate",
        ignore_result=True,
        bind=True,
    )
    def generate_certificate(self, job_id: str) -> None:
        try:
            handler = handler_factory()
            handler.handle(GenerateCertificateCommand(job_id=UUID(job_id)))

        except TemporaryStorageError as exc:
            if self.request.retries >= 3:
                failure_handler = failure_handler_factory()

                failure_handler.handle(
                    command=MarkJobFailedCommand(
                        job_id=UUID(job_id),
                        error_message="Document generation failed",
                    )
                )
                return

            raise self.retry(exc=exc, countdown=2**self.request.retries)

        except PermanentDocumentError:
            return
