import json

from aiokafka import AIOKafkaProducer

from schedule_service.application.ports.outbox_repository import PendingOutboxEvent


class KafkaEventPublisher:
    def __init__(self, producer: AIOKafkaProducer, topic: str) -> None:
        self._producer = producer
        self._topic = topic

    async def publish(self, event: PendingOutboxEvent) -> None:
        envelope = {
            "event_id": event.id,
            "event_type": event.event_type,
            "occurred_at": event.created_at.isoformat(),
            "payload": event.payload,
        }

        await self._producer.send_and_wait(
            self._topic,
            json.dumps(envelope, separators=(",", ":")).encode(),
            key=str(event.payload["lesson_id"]).encode(),
        )
