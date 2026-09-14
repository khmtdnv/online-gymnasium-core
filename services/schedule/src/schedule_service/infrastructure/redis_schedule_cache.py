import json
from datetime import date, datetime

import redis.asyncio as redis

from schedule_service.domain.lesson import Lesson


class RedisScheduleCache:
    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    def _key(self, *, class_id: int, day: date) -> str:
        return f"schedule:class:{class_id}:date:{day.isoformat()}"

    async def get(self, *, class_id: int, day: date) -> list[Lesson] | None:
        serialized = await self._client.get(self._key(class_id=class_id, day=day))

        if serialized is None:
            return None

        payload = json.loads(serialized)

        lessons = []
        for lesson in payload:
            lessons.append(
                Lesson(
                    id=lesson["id"],
                    class_id=lesson["class_id"],
                    teacher_id=lesson["teacher_id"],
                    subject_id=lesson["subject_id"],
                    starts_at=datetime.fromisoformat(lesson["starts_at"]),
                    ends_at=datetime.fromisoformat(lesson["ends_at"]),
                    status=lesson["status"],
                    version=lesson["version"],
                )
            )

        return lessons

    async def set(
        self,
        *,
        class_id: int,
        day: date,
        lessons: list[Lesson],
        ttl_seconds: int,
    ) -> None:
        payload = []

        for lesson in lessons:
            payload.append(
                {
                    "id": lesson.id,
                    "class_id": lesson.class_id,
                    "teacher_id": lesson.teacher_id,
                    "subject_id": lesson.subject_id,
                    "starts_at": lesson.starts_at.isoformat(),
                    "ends_at": lesson.ends_at.isoformat(),
                    "status": lesson.status,
                    "version": lesson.version,
                }
            )

        await self._client.set(
            self._key(class_id=class_id, day=day),
            json.dumps(payload),
            ex=ttl_seconds,
        )

    async def aclose(self) -> None:
        await self._client.aclose()
