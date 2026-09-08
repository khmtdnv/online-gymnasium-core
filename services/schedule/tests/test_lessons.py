from typing import Self

from fastapi.testclient import TestClient

from schedule_service.app import create_app
from schedule_service.application.errors import ScheduleConflict
from schedule_service.config import Settings
from schedule_service.domain.lesson import Lesson
from schedule_service.infrastructure.database import create_engine


class FakeLessonRepository:
    def __init__(self) -> None:
        self.saved: Lesson | None = None

    async def add(self, lesson: Lesson) -> Lesson:
        self.saved = lesson

        return Lesson(
            id=501,
            class_id=lesson.class_id,
            teacher_id=lesson.teacher_id,
            subject_id=lesson.subject_id,
            starts_at=lesson.starts_at,
            ends_at=lesson.ends_at,
            status=lesson.status,
            version=lesson.version,
        )


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.lessons = FakeLessonRepository()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


def test_create_lesson_endpoint() -> None:
    test_app_name = "Test Schedule Service"
    test_settings = Settings(
        app_name=test_app_name,
        database_url="postgresql+asyncpg://schedule:password@localhost:5432/schedule",
        redis_url="test_url",
        rabbitmq_url="test_url",
    )
    test_engine = create_engine(url=test_settings.database_url)
    fake_uow = FakeUnitOfWork()
    test_app = create_app(test_settings, test_engine, lambda: fake_uow)

    with TestClient(test_app) as test_client:
        request_body = {
            "class_id": 10,
            "teacher_id": 100,
            "subject_id": 1000,
            "starts_at": "2026-09-08T10:00:00Z",
            "ends_at": "2026-09-08T11:00:00Z",
        }
        response = test_client.post("/lessons", json=request_body)

        assert response.status_code == 201

        response_body = response.json()
        assert response_body["id"] == 501
        assert response_body["status"] == "planned"
        assert response_body["version"] == 1

    assert fake_uow.lessons.saved is not None
    assert fake_uow.lessons.saved.class_id == 10


def test_create_lesson_rejects_non_positive_interval() -> None:
    test_app_name = "Test Schedule Service"
    test_settings = Settings(
        app_name=test_app_name,
        database_url="postgresql+asyncpg://schedule:password@localhost:5432/schedule",
        redis_url="test_url",
        rabbitmq_url="test_url",
    )
    test_engine = create_engine(url=test_settings.database_url)
    fake_uow = FakeUnitOfWork()
    test_app = create_app(test_settings, test_engine, lambda: fake_uow)

    with TestClient(test_app, raise_server_exceptions=False) as test_client:
        request_body = {
            "class_id": 10,
            "teacher_id": 100,
            "subject_id": 1000,
            "starts_at": "2026-09-08T10:00:00Z",
            "ends_at": "2026-09-08T10:00:00Z",
        }
        response = test_client.post("/lessons", json=request_body)

        assert response.status_code == 422
        assert response.json() == {"detail": "starts_at must be before ends_at"}

    assert fake_uow.lessons.saved is None


class ConflictingLessonRepository:
    async def add(self, lesson: Lesson) -> Lesson:
        raise ScheduleConflict


def test_create_lesson_returns_conflict_for_schedule_conflict() -> None:
    test_app_name = "Test Schedule Service"
    test_settings = Settings(
        app_name=test_app_name,
        database_url="postgresql+asyncpg://schedule:password@localhost:5432/schedule",
        redis_url="test_url",
        rabbitmq_url="test_url",
    )
    test_engine = create_engine(url=test_settings.database_url)
    fake_uow = FakeUnitOfWork()
    fake_uow.lessons = ConflictingLessonRepository()
    test_app = create_app(test_settings, test_engine, lambda: fake_uow)

    with TestClient(test_app, raise_server_exceptions=False) as test_client:
        request_body = {
            "class_id": 10,
            "teacher_id": 100,
            "subject_id": 1000,
            "starts_at": "2026-09-08T10:00:00Z",
            "ends_at": "2026-09-08T11:00:00Z",
        }
        response = test_client.post("/lessons", json=request_body)

        assert response.status_code == 409
        assert response.json() == {
            "detail": "Lesson conflicts with existing schedule",
        }
