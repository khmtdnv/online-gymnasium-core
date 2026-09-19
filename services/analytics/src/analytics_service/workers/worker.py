import asyncio
import base64
import json
import logging
from datetime import UTC, datetime

import clickhouse_connect
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

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
    producer = AIOKafkaProducer(bootstrap_servers=settings.kafka_bootstrap_servers)
    client = clickhouse_connect.get_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
    )
    repository = ClickHouseSnapshotRepository(client)

    try:
        await consumer.start()
        await producer.start()

        async for message in consumer:
            try:
                try:
                    envelope = json.loads(message.value)
                    snapshot = parse_lesson_snapshot(envelope)
                except (
                    json.JSONDecodeError,
                    UnicodeDecodeError,
                    TypeError,
                    ValueError,
                ) as exc:
                    dlq_envelope = {
                        "source_topic": message.topic,
                        "source_partition": message.partition,
                        "source_offset": message.offset,
                        "failed_at": datetime.now(UTC).isoformat(),
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                        "original_value_base64": base64.b64encode(message.value).decode(
                            "ascii"
                        ),
                    }
                    await producer.send_and_wait(
                        settings.analytics_dlq_topic,
                        json.dumps(
                            dlq_envelope,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode(),
                    )
                    await consumer.commit()

                    continue

                if snapshot is not None:
                    await repository.add(snapshot)

                await consumer.commit()
            except Exception:
                logger.exception("Analytics worker failed to process Kafka event")
                raise
    finally:
        await consumer.stop()
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(run())
