import asyncio
import json
import logging
from datetime import date

import redis.asyncio as redis
from aiokafka import AIOKafkaConsumer

from schedule_service.application.cache_invalidator import CacheInvalidator
from schedule_service.domain.events import ScheduleChanged
from schedule_service.infrastructure.redis_schedule_cache import RedisScheduleCache
from schedule_service.workers.config import InvalidatorSettings

logger = logging.getLogger(__name__)


async def run() -> None:
    settings = InvalidatorSettings()
    consumer = AIOKafkaConsumer(
        "schedule.lessons",
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id="schedule-cache-invalidator",
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    cache = RedisScheduleCache(redis_client)
    invalidator = CacheInvalidator(cache)

    try:
        await consumer.start()

        async for message in consumer:
            try:
                envelope = json.loads(message.value)
                if envelope["event_type"] == "schedule.changed":
                    payload = envelope["payload"]
                    event = ScheduleChanged(
                        lesson_id=payload["lesson_id"],
                        class_id=payload["class_id"],
                        affected_dates=tuple(
                            date.fromisoformat(day) for day in payload["affected_dates"]
                        ),
                    )
                    await invalidator.handle(event)

                await consumer.commit()
            except Exception:
                logger.exception("Cache invalidator failed to process Kafka event")
                raise
    finally:
        try:
            await consumer.stop()
        finally:
            await cache.aclose()


if __name__ == "__main__":
    asyncio.run(run())
