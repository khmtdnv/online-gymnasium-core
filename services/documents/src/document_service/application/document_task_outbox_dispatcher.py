from document_service.application.ports.task_publisher import TaskPublisher
from document_service.application.ports.unit_of_work import DocumentUnitOfWorkFactory


class DocumentTaskOutboxDispatcher:
    def __init__(
        self,
        uow_factory: DocumentUnitOfWorkFactory,
        publisher: TaskPublisher,
        batch_size: int = 100,
    ) -> None:
        self._uow_factory = uow_factory
        self._publisher = publisher
        self._batch_size = batch_size

    def run_once(self) -> int:
        with self._uow_factory() as uow:
            tasks = uow.outbox.get_pending(limit=self._batch_size)

        for task in tasks:
            self._publisher.publish(task)

            with self._uow_factory() as uow:
                uow.outbox.mark_published(task_id=task.id)

        return len(tasks)
