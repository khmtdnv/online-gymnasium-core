from typing import Protocol

from schedule_service.application.ports.outbox_repository import PendingOutboxEvent


class EventPublisher(Protocol):
    async def publish(self, event: PendingOutboxEvent) -> None: ...
