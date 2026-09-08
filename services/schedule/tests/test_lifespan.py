from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine

from schedule_service.app import create_app
from schedule_service.application.ports.unit_of_work import UnitOfWorkFactory
from schedule_service.config import Settings


def test_app_disposes_engine_on_shutdown(unused_uow_factory: UnitOfWorkFactory) -> None:
    test_settings = Settings(
        database_url="postgresql+asyncpg://schedule:password@localhost:5432/schedule",
        redis_url="Test url",
        rabbitmq_url="Test url",
    )
    engine_mock = AsyncMock(spec=AsyncEngine)
    test_app = create_app(test_settings, engine_mock, unused_uow_factory)
    with TestClient(test_app):
        pass

    engine_mock.dispose.assert_awaited_once()
