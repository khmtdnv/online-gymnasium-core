from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from aiokafka import AIOKafkaProducer

from schedule_service.application.ports.outbox_repository import PendingOutboxEvent


@pytest.mark.anyio
async def test_kafka_publisher_sends_documented_json_envelope_with_lesson_key() -> None:
    from schedule_service.infrastructure.kafka_event_publisher import KafkaEventPublisher

    producer = AsyncMock(spec=AIOKafkaProducer)
    publisher = KafkaEventPublisher(producer=producer, topic="schedule.lessons")
    event = PendingOutboxEvent(
        id=42,
        event_type="lesson.created",
        payload={"lesson_id": 501},
        created_at=datetime(2026, 9, 13, 12, tzinfo=UTC),
    )

    await publisher.publish(event)

    producer.send_and_wait.assert_awaited_once_with(
        "schedule.lessons",
        b'{"event_id":42,"event_type":"lesson.created","occurred_at":"2026-09-13T12:00:00+00:00","payload":{"lesson_id":501}}',
        key=b"501",
    )
