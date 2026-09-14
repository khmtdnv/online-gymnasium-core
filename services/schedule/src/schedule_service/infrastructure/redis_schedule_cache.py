import json
from datetime import date, datetime

import redis.asyncio as redis

from schedule_service.domain.lesson import Lesson

_RELEASE_LOCK_SCRIPT = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
end
return 0
"""

_SET_IF_GENERATION_SCRIPT = """
local current = redis.call("GET", KEYS[2]) or "0"

if current ~= ARGV[1] then
    return 0
end

redis.call("SET", KEYS[1], ARGV[2], "EX", ARGV[3])
return 1
"""

_INVALIDATE_SCRIPT = """
redis.call("INCR", KEYS[2])
return redis.call("DEL", KEYS[1])
"""


class RedisScheduleCache:
    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    def _key(self, *, class_id: int, day: date) -> str:
        return f"schedule:class:{class_id}:date:{day.isoformat()}"

    def _generation_key(self, *, class_id: int, day: date) -> str:
        return f"{self._key(class_id=class_id, day=day)}:gen"

    def _lock_key(self, *, class_id: int, day: date) -> str:
        return f"{self._key(class_id=class_id, day=day)}:lock"

    @staticmethod
    def _serialize(lessons: list[Lesson]) -> str:
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

        return json.dumps(payload)

    @staticmethod
    def _deserialize(serialized: str) -> list[Lesson]:
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

    async def get(self, *, class_id: int, day: date) -> list[Lesson] | None:
        serialized = await self._client.get(self._key(class_id=class_id, day=day))

        if serialized is None:
            return None

        return self._deserialize(serialized)

    async def get_generation(self, *, class_id: int, day: date) -> int:
        generation = await self._client.get(
            self._generation_key(class_id=class_id, day=day)
        )

        if generation is None:
            return 0

        return int(generation)

    async def try_acquire_fill_lock(
        self,
        *,
        class_id: int,
        day: date,
        token: str,
        ttl_ms: int,
    ) -> bool:
        result = await self._client.set(
            self._lock_key(class_id=class_id, day=day),
            token,
            nx=True,
            px=ttl_ms,
        )
        return result is True

    async def release_fill_lock(
        self,
        *,
        class_id: int,
        day: date,
        token: str,
    ) -> None:
        await self._client.eval(
            _RELEASE_LOCK_SCRIPT,
            1,
            self._lock_key(class_id=class_id, day=day),
            token,
        )

    async def set_if_generation(
        self,
        *,
        class_id: int,
        day: date,
        lessons: list[Lesson],
        ttl_seconds: int,
        expected_generation: int,
    ) -> bool:
        result = await self._client.eval(
            _SET_IF_GENERATION_SCRIPT,
            2,
            self._key(class_id=class_id, day=day),
            self._generation_key(class_id=class_id, day=day),
            str(expected_generation),
            self._serialize(lessons),
            str(ttl_seconds),
        )
        return bool(result)

    async def invalidate(
        self,
        *,
        class_id: int,
        days: tuple[date, ...],
    ) -> None:
        if not days:
            return

        for day in days:
            await self._client.eval(
                _INVALIDATE_SCRIPT,
                2,
                self._key(class_id=class_id, day=day),
                self._generation_key(class_id=class_id, day=day),
            )

    async def aclose(self) -> None:
        await self._client.aclose()
