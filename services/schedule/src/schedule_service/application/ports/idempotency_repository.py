from dataclasses import dataclass
from typing import Protocol

from schedule_service.domain.lesson import Lesson


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    request_hash: str
    lesson: Lesson | None


class IdempotencyRepository(Protocol):
    async def claim(self, operation: str, key: str, request_hash: str) -> IdempotencyRecord | None: ...
    async def complete(self, operation: str, key: str, lesson: Lesson) -> None: ...
