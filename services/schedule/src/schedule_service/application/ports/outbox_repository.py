from typing import Protocol

from schedule_service.domain.events import LessonCreated


class OutboxRepository(Protocol):
    async def add(self, event: LessonCreated): ...
