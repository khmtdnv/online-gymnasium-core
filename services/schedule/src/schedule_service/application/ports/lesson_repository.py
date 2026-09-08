from typing import Protocol

from schedule_service.domain.lesson import Lesson


class LessonRepository(Protocol):
    async def add(self, lesson: Lesson) -> Lesson: ...
