from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import Mock

from fastapi.testclient import TestClient

from analytics_service.application.workload import ClassDailyWorkload


class FakeWorkloadRepository:
    def __init__(self, workload: ClassDailyWorkload | None) -> None:
        self._workload = workload

    async def get(
        self,
        *,
        class_id: int,
        day: date,
    ) -> ClassDailyWorkload | None:
        return self._workload


class FailingWorkloadRepository:
    async def get(
        self,
        *,
        class_id: int,
        day: date,
    ) -> ClassDailyWorkload | None:
        raise RuntimeError("ClickHouse connection refused")


def workload() -> ClassDailyWorkload:
    return ClassDailyWorkload(
        class_id=10,
        day=date(2026, 10, 2),
        planned_lessons_count=1,
        planned_minutes=60,
        refreshed_at=datetime(2026, 9, 19, 8, tzinfo=UTC),
    )


def test_get_workload_returns_materialized_result() -> None:
    from analytics_service.api.app import create_app

    app = create_app(repository_factory=lambda: FakeWorkloadRepository(workload()))

    with TestClient(app) as client:
        response = client.get(
            "/workload",
            params={"class_id": 10, "day": "2026-10-02"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "class_id": 10,
        "day": "2026-10-02",
        "planned_lessons_count": 1,
        "planned_minutes": 60,
        "refreshed_at": "2026-09-19T08:00:00Z",
    }


def test_get_workload_uses_fastapi_repository_dependency_override() -> None:
    from analytics_service.api.app import create_app
    from analytics_service.api.dependencies import get_workload_repository

    repository_factory = Mock()
    app = create_app(repository_factory=repository_factory)
    app.dependency_overrides[get_workload_repository] = lambda: FakeWorkloadRepository(
        workload()
    )

    with TestClient(app) as client:
        response = client.get(
            "/workload",
            params={"class_id": 10, "day": "2026-10-02"},
        )

    assert response.status_code == 200
    repository_factory.assert_not_called()


def test_get_workload_returns_404_when_workload_is_missing() -> None:
    from analytics_service.api.app import create_app

    app = create_app(repository_factory=lambda: FakeWorkloadRepository(None))

    with TestClient(app) as client:
        response = client.get(
            "/workload",
            params={"class_id": 10, "day": "2026-10-02"},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Workload was not found"}


def test_get_workload_returns_503_when_clickhouse_query_fails() -> None:
    from analytics_service.api.app import create_app

    app = create_app(repository_factory=FailingWorkloadRepository)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/workload",
            params={"class_id": 10, "day": "2026-10-02"},
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Analytics storage is unavailable"}


def test_get_workload_rejects_non_positive_class_id() -> None:
    from analytics_service.api.app import create_app

    repository_factory = Mock()
    app = create_app(repository_factory=repository_factory)

    with TestClient(app) as client:
        response = client.get(
            "/workload",
            params={"class_id": 0, "day": "2026-10-02"},
        )

    assert response.status_code == 422


def test_get_workload_rejects_invalid_day() -> None:
    from analytics_service.api.app import create_app

    repository_factory = Mock()
    app = create_app(repository_factory=repository_factory)

    with TestClient(app) as client:
        response = client.get(
            "/workload",
            params={"class_id": 10, "day": "not-a-date"},
        )

    assert response.status_code == 422


def test_live_endpoint_does_not_create_workload_repository() -> None:
    from analytics_service.api.app import create_app

    repository_factory = Mock()
    app = create_app(repository_factory=repository_factory)

    with TestClient(app) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    repository_factory.assert_not_called()


def test_compose_defines_independent_analytics_api_service() -> None:
    compose = (Path(__file__).parents[3] / "compose.yaml").read_text()

    assert "  analytics-api:" in compose
    assert "context: ./services/analytics" in compose
    assert "analytics_service.main:app" in compose
    assert '"8001:8000"' in compose
    assert "CLICKHOUSE_HOST: clickhouse" in compose
    assert "CLICKHOUSE_PORT: 8123" in compose
    assert "clickhouse:\n        condition: service_healthy" in compose
    assert "restart: unless-stopped" in compose
    assert "http://127.0.0.1:8000/health/live" in compose
