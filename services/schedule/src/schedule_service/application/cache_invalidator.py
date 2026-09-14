from schedule_service.application.ports.schedule_cache import ScheduleCache
from schedule_service.domain.events import ScheduleChanged


class CacheInvalidator:
    def __init__(self, cache: ScheduleCache) -> None:
        self._cache = cache

    async def handle(self, event: ScheduleChanged) -> None:
        await self._cache.invalidate(class_id=event.class_id, days=event.affected_dates)
