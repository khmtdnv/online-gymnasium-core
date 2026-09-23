from typing import Protocol

from document_service.application.ports.document_task_outbox_repository import (
    PendingDocumentTask,
)


class TaskPublisher(Protocol):
    def publish(self, task: PendingDocumentTask) -> None: ...
