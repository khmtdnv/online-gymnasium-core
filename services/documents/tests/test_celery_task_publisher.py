from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

from celery import Celery

from document_service.application.ports.document_task_outbox_repository import (
    PendingDocumentTask,
)


def test_celery_publisher_sends_task_name_with_document_job_id() -> None:
    from document_service.infrastructure.celery_task_publisher import (
        CeleryTaskPublisher,
    )

    celery_app = Mock(spec=Celery)
    task = PendingDocumentTask(
        id=uuid4(),
        document_job_id=uuid4(),
        task_name="documents.generate_certificate",
        created_at=datetime(2026, 9, 22, tzinfo=UTC),
    )
    publisher = CeleryTaskPublisher(celery_app)

    publisher.publish(task)

    celery_app.send_task.assert_called_once_with(
        "documents.generate_certificate",
        args=[str(task.document_job_id)],
    )
