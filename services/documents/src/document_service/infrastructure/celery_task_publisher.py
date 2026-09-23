from celery import Celery

from document_service.application.ports.document_task_outbox_repository import (
    PendingDocumentTask,
)


class CeleryTaskPublisher:
    def __init__(self, celery_app: Celery) -> None:
        self._celery_app = celery_app

    def publish(self, task: PendingDocumentTask) -> None:
        self._celery_app.send_task(task.task_name, args=[str(task.document_job_id)])
