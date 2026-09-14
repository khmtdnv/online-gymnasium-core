from datetime import UTC, date, datetime
from typing import Self

import pytest
from fastapi.testclient import TestClient

from schedule_service.app import create_app
from schedule_service.config import Settings
from schedule_service.domain.lesson import Lesson
from schedule_service.infrastructure.database import create_engine


class ListingLessonRepository:
    def __init__(self) -> None:
        self.query: tuple[int, date] | None = None
        self.query_count = 0

    async def get_class_schedule(self, *, class_id: int, day: date) -> list[Lesson]:
        self.query = (class_id, day)
        self.query_count += 1
        return [
            Lesson(
                id=501,
                class_id=class_id,
                teacher_id=100,
                subject_id=1000,
                starts_at=datetime(2026, 9, 10, 10, tzinfo=UTC),
                ends_at=datetime(2026, 9, 10, 11, tzinfo=UTC),
                status="planned",
                version=1,
            )
        ]


class InMemoryScheduleCache:
    def __init__(self) -> None:
        self.entries: dict[tuple[int, date], list[Lesson]] = {}
        self.ttls: list[int] = []
        self.generation = 0
        self.lock_results: list[bool] = []
        self.set_results: list[bool] = []
        self.released_tokens: list[str] = []

    async def get(self, *, class_id: int, day: date) -> list[Lesson] | None:
        return self.entries.get((class_id, day))

    async def get_generation(self, *, class_id: int, day: date) -> int:
        return self.generation

    async def try_acquire_fill_lock(
        self,
        *,
        class_id: int,
        day: date,
        token: str,
        ttl_ms: int,
    ) -> bool:
        if self.lock_results:
            return self.lock_results.pop(0)
        return True

    async def release_fill_lock(
        self,
        *,
        class_id: int,
        day: date,
        token: str,
    ) -> None:
        self.released_tokens.append(token)

    async def set_if_generation(
        self,
        *,
        class_id: int,
        day: date,
        lessons: list[Lesson],
        ttl_seconds: int,
        expected_generation: int,
    ) -> bool:
        stored = self.set_results.pop(0) if self.set_results else True
        if not stored:
            return False

        self.entries[(class_id, day)] = lessons
        self.ttls.append(ttl_seconds)
        return True

    async def invalidate(self, *, class_id: int, days: tuple[date, ...]) -> None:
        self.generation += 1
        for day in days:
            self.entries.pop((class_id, day), None)

    async def aclose(self) -> None:
        return None


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.lessons = ListingLessonRepository()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


def create_handler(
    fake_uow: FakeUnitOfWork,
    cache: InMemoryScheduleCache,
    *,
    retry_limit: int = 20,
):
    from schedule_service.application.list_lessons import ListLessonsHandler

    return ListLessonsHandler(
        uow_factory=lambda: fake_uow,
        cache=cache,
        schedule_cache_ttl_seconds=60,
        schedule_cache_lock_ttl_ms=5000,
        schedule_cache_lock_retry_delay_ms=1,
        schedule_cache_lock_retry_limit=retry_limit,
    )


def test_list_lessons_endpoint_returns_planned_class_schedule_for_day() -> None:
    settings = Settings(
        app_name="Test Schedule Service",
        database_url="postgresql+asyncpg://schedule:password@localhost:5432/schedule",
        redis_url="test_url",
        rabbitmq_url="test_url",
    )
    engine = create_engine(url=settings.database_url)
    fake_uow = FakeUnitOfWork()
    cache = InMemoryScheduleCache()
    app = create_app(settings, engine, lambda: fake_uow, cache)

    with TestClient(app) as client:
        response = client.get("/lessons", params={"class_id": 10, "date": "2026-09-10"})

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": 501,
            "class_id": 10,
            "teacher_id": 100,
            "subject_id": 1000,
            "starts_at": "2026-09-10T10:00:00Z",
            "ends_at": "2026-09-10T11:00:00Z",
            "status": "planned",
            "version": 1,
        }
    ]
    assert fake_uow.lessons.query == (10, date(2026, 9, 10))


@pytest.mark.anyio
async def test_handler_returns_cached_schedule_without_database_read() -> None:
    from schedule_service.application.list_lessons import (
        ListLessonsQuery,
    )

    fake_uow = FakeUnitOfWork()
    cache = InMemoryScheduleCache()
    cached_lesson = Lesson(
        id=502,
        class_id=10,
        teacher_id=100,
        subject_id=1000,
        starts_at=datetime(2026, 9, 10, 12, tzinfo=UTC),
        ends_at=datetime(2026, 9, 10, 13, tzinfo=UTC),
        status="planned",
        version=1,
    )
    cache.entries[(10, date(2026, 9, 10))] = [cached_lesson]
    handler = create_handler(fake_uow, cache)

    lessons = await handler.handle(ListLessonsQuery(class_id=10, day=date(2026, 9, 10)))

    assert lessons == [cached_lesson]
    assert fake_uow.lessons.query is None


@pytest.mark.anyio
async def test_handler_caches_database_schedule_for_60_seconds_after_cache_miss() -> (
    None
):
    from schedule_service.application.list_lessons import (
        ListLessonsQuery,
    )

    fake_uow = FakeUnitOfWork()
    cache = InMemoryScheduleCache()
    handler = create_handler(fake_uow, cache)

    lessons = await handler.handle(ListLessonsQuery(class_id=10, day=date(2026, 9, 10)))

    assert [lesson.id for lesson in lessons] == [501]
    assert fake_uow.lessons.query == (10, date(2026, 9, 10))
    assert cache.entries[(10, date(2026, 9, 10))] == lessons
    assert cache.ttls == [60]


@pytest.mark.anyio
async def test_handler_retries_database_read_after_generation_changed() -> None:
    from schedule_service.application.list_lessons import ListLessonsQuery

    fake_uow = FakeUnitOfWork()
    cache = InMemoryScheduleCache()
    cache.set_results = [False, True]
    handler = create_handler(fake_uow, cache)

    lessons = await handler.handle(ListLessonsQuery(class_id=10, day=date(2026, 9, 10)))

    assert [lesson.id for lesson in lessons] == [501]
    assert fake_uow.lessons.query_count == 2
    assert len(cache.released_tokens) == 2


def test_list_lessons_returns_503_when_cache_fill_lock_stays_busy() -> None:
    settings = Settings(
        app_name="Test Schedule Service",
        database_url="postgresql+asyncpg://schedule:password@localhost:5432/schedule",
        redis_url="test_url",
        rabbitmq_url="test_url",
        schedule_cache_lock_retry_delay_ms=1,
        schedule_cache_lock_retry_limit=1,
    )
    engine = create_engine(url=settings.database_url)
    fake_uow = FakeUnitOfWork()
    cache = InMemoryScheduleCache()
    cache.lock_results = [False]
    app = create_app(settings, engine, lambda: fake_uow, cache)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/lessons",
            params={"class_id": 10, "date": "2026-09-10"},
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Schedule cache is busy"}
    assert fake_uow.lessons.query is None
