from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from schedule_service.app import create_app
from schedule_service.config import Settings


def test_readiness_endpoint_checks_database() -> None:
    settings = Settings(
        app_name="Test Schedule Service",
        database_url="postgresql+asyncpg://schedule:password@localhost:5432/schedule",
        redis_url="redis://localhost:6379/0",
        rabbitmq_url="amqp://guest:guest@localhost:5672/",
    )

    engine_mock = AsyncMock(spec=AsyncEngine)
    connection_mock = AsyncMock()
    engine_mock.connect.return_value.__aenter__.return_value = connection_mock

    app = create_app(settings, engine_mock)

    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    engine_mock.connect.assert_called_once()
    connection_mock.execute.assert_awaited_once()


def test_readiness_endpoint_returns_503_when_database_is_unavailable() -> None:
    settings = Settings(
        app_name="Test Schedule Service",
        database_url="postgresql+asyncpg://schedule:password@localhost:5432/schedule",
        redis_url="redis://localhost:6379/0",
        rabbitmq_url="amqp://guest:guest@localhost:5672/",
    )

    engine_mock = AsyncMock(spec=AsyncEngine)
    engine_mock.connect.side_effect = SQLAlchemyError()
    test_app = create_app(settings=settings, engine=engine_mock)
    with TestClient(test_app, raise_server_exceptions=False) as test_client:
        response = test_client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database is unavailable"}
