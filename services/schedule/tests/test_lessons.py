from datetime import UTC, datetime
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


class UpdatingLessonRepository:
    async def get(self, lesson_id: int) -> Lesson | None:
        if lesson_id != 501:
            return None

        return Lesson(
            id=501,
            class_id=10,
            teacher_id=100,
            subject_id=1000,
            starts_at=datetime(2026, 9, 10, 10, tzinfo=UTC),
            ends_at=datetime(2026, 9, 10, 11, tzinfo=UTC),
            status="planned",
            version=3,
        )

    async def update(self, lesson: Lesson, expected_version: int) -> Lesson | None:
        return Lesson(
            id=lesson.id,
            class_id=lesson.class_id,
            teacher_id=lesson.teacher_id,
            subject_id=lesson.subject_id,
            starts_at=lesson.starts_at,
            ends_at=lesson.ends_at,
            status=lesson.status,
            version=4,
        )


class StaleVersionLessonRepository(UpdatingLessonRepository):
    async def update(self, lesson: Lesson, expected_version: int) -> Lesson | None:
        return None


class ConflictingUpdateLessonRepository(UpdatingLessonRepository):
    async def update(self, lesson: Lesson, expected_version: int) -> Lesson | None:
        raise ScheduleConflict


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


def test_update_lesson_endpoint() -> None:
    settings = Settings(
        app_name="Test Schedule Service",
        database_url="postgresql+asyncpg://schedule:password@localhost:5432/schedule",
        redis_url="test_url",
        rabbitmq_url="test_url",
    )
    engine = create_engine(url=settings.database_url)
    fake_uow = FakeUnitOfWork()
    fake_uow.lessons = UpdatingLessonRepository()
    app = create_app(settings, engine, lambda: fake_uow)

    with TestClient(app) as client:
        response = client.patch(
            "/lessons/501",
            json={
                "starts_at": "2026-09-10T12:00:00Z",
                "ends_at": "2026-09-10T13:00:00Z",
                "expected_version": 3,
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "id": 501,
        "class_id": 10,
        "teacher_id": 100,
        "subject_id": 1000,
        "starts_at": "2026-09-10T12:00:00Z",
        "ends_at": "2026-09-10T13:00:00Z",
        "status": "planned",
        "version": 4,
    }


def test_update_lesson_rejects_non_positive_interval() -> None:
    settings = Settings(
        app_name="Test Schedule Service",
        database_url="postgresql+asyncpg://schedule:password@localhost:5432/schedule",
        redis_url="test_url",
        rabbitmq_url="test_url",
    )
    engine = create_engine(url=settings.database_url)
    fake_uow = FakeUnitOfWork()
    fake_uow.lessons = UpdatingLessonRepository()
    app = create_app(settings, engine, lambda: fake_uow)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.patch(
            "/lessons/501",
            json={
                "starts_at": "2026-09-10T12:00:00Z",
                "ends_at": "2026-09-10T12:00:00Z",
                "expected_version": 3,
            },
        )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "starts_at must be before ends_at",
    }


def test_update_lesson_returns_not_found_for_missing_lesson() -> None:
    settings = Settings(
        app_name="Test Schedule Service",
        database_url="postgresql+asyncpg://schedule:password@localhost:5432/schedule",
        redis_url="test_url",
        rabbitmq_url="test_url",
    )
    engine = create_engine(url=settings.database_url)
    fake_uow = FakeUnitOfWork()
    fake_uow.lessons = UpdatingLessonRepository()
    app = create_app(settings, engine, lambda: fake_uow)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.patch(
            "/lessons/999",
            json={
                "starts_at": "2026-09-10T12:00:00Z",
                "ends_at": "2026-09-10T13:00:00Z",
                "expected_version": 3,
            },
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Lesson not found"}


def test_update_lesson_returns_conflict_for_stale_version() -> None:
    settings = Settings(
        app_name="Test Schedule Service",
        database_url="postgresql+asyncpg://schedule:password@localhost:5432/schedule",
        redis_url="test_url",
        rabbitmq_url="test_url",
    )
    engine = create_engine(url=settings.database_url)
    fake_uow = FakeUnitOfWork()
    fake_uow.lessons = StaleVersionLessonRepository()
    app = create_app(settings, engine, lambda: fake_uow)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.patch(
            "/lessons/501",
            json={
                "starts_at": "2026-09-10T12:00:00Z",
                "ends_at": "2026-09-10T13:00:00Z",
                "expected_version": 2,
            },
        )

    assert response.status_code == 409
    assert response.json() == {"detail": "Lesson version conflict"}


def test_update_lesson_returns_conflict_for_schedule_conflict() -> None:
    settings = Settings(
        app_name="Test Schedule Service",
        database_url="postgresql+asyncpg://schedule:password@localhost:5432/schedule",
        redis_url="test_url",
        rabbitmq_url="test_url",
    )
    engine = create_engine(url=settings.database_url)
    fake_uow = FakeUnitOfWork()
    fake_uow.lessons = ConflictingUpdateLessonRepository()
    app = create_app(settings, engine, lambda: fake_uow)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.patch(
            "/lessons/501",
            json={
                "starts_at": "2026-09-10T12:00:00Z",
                "ends_at": "2026-09-10T13:00:00Z",
                "expected_version": 3,
            },
        )

    assert response.status_code == 409
    assert response.json() == {"detail": "Lesson conflicts with existing schedule"}
