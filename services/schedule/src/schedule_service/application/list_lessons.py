import asyncio
import secrets
from dataclasses import dataclass
from datetime import date

from schedule_service.application.errors import ScheduleCacheBusy
from schedule_service.application.ports.schedule_cache import ScheduleCache
from schedule_service.application.ports.unit_of_work import UnitOfWorkFactory
from schedule_service.domain.lesson import Lesson


@dataclass(frozen=True, slots=True)
class ListLessonsQuery:
    class_id: int
    day: date


class ListLessonsHandler:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        cache: ScheduleCache,
        schedule_cache_ttl_seconds: int,
        schedule_cache_lock_ttl_ms: int,
        schedule_cache_lock_retry_delay_ms: int,
        schedule_cache_lock_retry_limit: int,
    ) -> None:
        self._uow_factory = uow_factory
        self._cache = cache
        self._schedule_cache_ttl_seconds = schedule_cache_ttl_seconds
        self._schedule_cache_lock_ttl_ms = schedule_cache_lock_ttl_ms
        self._schedule_cache_lock_retry_delay_ms = schedule_cache_lock_retry_delay_ms
        self._schedule_cache_lock_retry_limit = schedule_cache_lock_retry_limit

    async def _read_from_database(
        self,
        query: ListLessonsQuery,
    ) -> list[Lesson]:
        async with self._uow_factory() as uow:
            return await uow.lessons.get_class_schedule(
                class_id=query.class_id,
                day=query.day,
            )

    async def handle(self, query: ListLessonsQuery) -> list[Lesson]:
        for _ in range(self._schedule_cache_lock_retry_limit):
            cached_lessons = await self._cache.get(
                class_id=query.class_id,
                day=query.day,
            )
            if cached_lessons is not None:
                return cached_lessons

            token = secrets.token_urlsafe(32)
            acquired = await self._cache.try_acquire_fill_lock(
                class_id=query.class_id,
                day=query.day,
                token=token,
                ttl_ms=self._schedule_cache_lock_ttl_ms,
            )
            if not acquired:
                await asyncio.sleep(self._schedule_cache_lock_retry_delay_ms / 1000)
                continue

            try:
                cached_lessons = await self._cache.get(
                    class_id=query.class_id,
                    day=query.day,
                )
                if cached_lessons is not None:
                    return cached_lessons

                generation = await self._cache.get_generation(
                    class_id=query.class_id,
                    day=query.day,
                )
                lessons = await self._read_from_database(query)

                stored = await self._cache.set_if_generation(
                    class_id=query.class_id,
                    day=query.day,
                    lessons=lessons,
                    ttl_seconds=self._schedule_cache_ttl_seconds,
                    expected_generation=generation,
                )
                if stored:
                    return lessons
            finally:
                await self._cache.release_fill_lock(
                    class_id=query.class_id,
                    day=query.day,
                    token=token,
                )

        raise ScheduleCacheBusy
