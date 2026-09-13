from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from schedule_service.domain.events import LessonCreated


@dataclass(frozen=True, slots=True)
class PendingOutboxEvent:
    id: int
    event_type: str
    payload: dict[str, object]
    created_at: datetime


class OutboxRepository(Protocol):
    async def add(self, event: LessonCreated) -> None: ...
    async def get_pending(self, *, limit: int) -> list[PendingOutboxEvent]: ...
    async def mark_published(self, *, event_id: int) -> None: ...
