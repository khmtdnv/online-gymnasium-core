from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine

from schedule_service.app import create_app
from schedule_service.config import Settings
from schedule_service.infrastructure.database import create_engine


def test_liveness_endpoint_returns_ok() -> None:
    test_settings = Settings(
        app_name="Test App",
        database_url="postgresql+asyncpg://schedule:password@localhost:5432/schedule",
        redis_url="Test URL",
        rabbitmq_url="Test URL",
    )
    test_engine: AsyncEngine = create_engine(test_settings.database_url)
    test_app = create_app(test_settings, test_engine)
    with TestClient(test_app) as test_client:
        response = test_client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
