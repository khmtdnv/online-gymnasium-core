import asyncio
import json
import logging

import clickhouse_connect
from aiokafka import AIOKafkaConsumer

from analytics_service.application.snapshot import parse_lesson_snapshot
from analytics_service.config import AnalyticsSettings
from analytics_service.infrastructure.clickhouse_snapshot_repository import (
    ClickHouseSnapshotRepository,
)

logger = logging.getLogger(__name__)


async def run() -> None:
    settings = AnalyticsSettings()

    consumer = AIOKafkaConsumer(
        "schedule.lessons",
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id="schedule-analytics",
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    client = clickhouse_connect.get_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
    )
    repository = ClickHouseSnapshotRepository(client)

    try:
        await consumer.start()

        async for message in consumer:
            try:
                envelope = json.loads(message.value)
                snapshot = parse_lesson_snapshot(envelope)

                if snapshot is not None:
                    await repository.add(snapshot)

                await consumer.commit()
            except Exception:
                logger.exception("Analytics worker failed to process Kafka event")
                raise
    finally:
        await consumer.stop()


if __name__ == "__main__":
    asyncio.run(run())
