import asyncio
import logging

from aiokafka import AIOKafkaProducer

from schedule_service.application.outbox_relay import OutboxRelay
from schedule_service.infrastructure.database import (
    create_engine,
    create_session_factory,
)
from schedule_service.infrastructure.kafka_event_publisher import KafkaEventPublisher
from schedule_service.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from schedule_service.workers.config import RelaySettings

logger = logging.getLogger(__name__)


async def run() -> None:
    settings = RelaySettings()
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers, acks="all"
    )
    publisher = KafkaEventPublisher(producer, topic="schedule.lessons")
    relay = OutboxRelay(
        uow_factory=lambda: SqlAlchemyUnitOfWork(session_factory), publisher=publisher
    )

    try:
        await producer.start()

        while True:
            try:
                published = await relay.run_once()
            except Exception:
                logger.exception("Outbox relay failed to publish pending events")
                published = 0

            await asyncio.sleep(0 if published else 1)
    finally:
        await producer.stop()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
