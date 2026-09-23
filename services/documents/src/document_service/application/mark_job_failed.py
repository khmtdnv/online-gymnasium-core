from dataclasses import dataclass
from uuid import UUID

from document_service.application.ports.unit_of_work import DocumentUnitOfWorkFactory


@dataclass(frozen=True, slots=True)
class MarkJobFailedCommand:
    job_id: UUID
    error_message: str


class MarkJobFailedHandler:
    def __init__(self, uow_factory: DocumentUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def handle(self, command: MarkJobFailedCommand) -> None:
        with self._uow_factory() as uow:
            uow.documents.mark_failed(command.job_id, command.error_message)
