from datetime import date
from unittest.mock import AsyncMock

import pytest

from schedule_service.application.ports.schedule_cache import ScheduleCache
from schedule_service.domain.events import ScheduleChanged


@pytest.mark.anyio
async def test_invalidator_deletes_schedule_cache_keys_for_changed_lesson() -> None:
    from schedule_service.application.cache_invalidator import CacheInvalidator

    cache = AsyncMock(spec=ScheduleCache)
    invalidator = CacheInvalidator(cache)
    event = ScheduleChanged(
        lesson_id=501,
        class_id=10,
        affected_dates=(date(2026, 9, 10), date(2026, 9, 11)),
    )

    await invalidator.handle(event)

    cache.invalidate.assert_awaited_once_with(
        class_id=10,
        days=(date(2026, 9, 10), date(2026, 9, 11)),
    )
