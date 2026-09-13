from schedule_service.application.ports.event_publisher import EventPublisher
from schedule_service.application.ports.unit_of_work import UnitOfWorkFactory


class OutboxRelay:
    def __init__(self, uow_factory: UnitOfWorkFactory, publisher: EventPublisher, batch_size: int = 100) -> None:
        self._uow_factory = uow_factory
        self._publisher = publisher
        self._batch_size = batch_size

    async def run_once(self) -> int:
        async with self._uow_factory() as uow:
            events = await uow.outbox.get_pending(limit=self._batch_size)

        for event in events:
            await self._publisher.publish(event)

            async with self._uow_factory() as uow:
                await uow.outbox.mark_published(event_id=event.id)

        return len(events)
