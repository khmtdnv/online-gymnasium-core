from datetime import UTC, date, datetime
from typing import Self

from fastapi.testclient import TestClient

from schedule_service.app import create_app
from schedule_service.config import Settings
from schedule_service.domain.lesson import Lesson
from schedule_service.infrastructure.database import create_engine


class ListingLessonRepository:
    def __init__(self) -> None:
        self.query: tuple[int, date] | None = None

    async def list_planned_for_class_on_day(self, *, class_id: int, day: date) -> list[Lesson]:
        self.query = (class_id, day)
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


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.lessons = ListingLessonRepository()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


def test_list_lessons_endpoint_returns_planned_class_schedule_for_day() -> None:
    settings = Settings(
        app_name="Test Schedule Service",
        database_url="postgresql+asyncpg://schedule:password@localhost:5432/schedule",
        redis_url="test_url",
        rabbitmq_url="test_url",
    )
    engine = create_engine(url=settings.database_url)
    fake_uow = FakeUnitOfWork()
    app = create_app(settings, engine, lambda: fake_uow)

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
