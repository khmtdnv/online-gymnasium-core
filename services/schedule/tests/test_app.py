import pytest
from conftest import NoopScheduleCache

from schedule_service.app import create_app
from schedule_service.application.ports.unit_of_work import UnitOfWorkFactory
from schedule_service.config import Settings
from schedule_service.infrastructure.database import create_engine


@pytest.mark.anyio
async def test_create_app_uses_title_from_settings(
    unused_uow_factory: UnitOfWorkFactory,
) -> None:
    test_app_name = "Test Schedule Service"
    test_settings = Settings(
        app_name=test_app_name,
        database_url="postgresql+asyncpg://schedule:password@localhost:5432/schedule",
        redis_url="test_url",
        rabbitmq_url="test_url",
    )
    test_engine = create_engine(url=test_settings.database_url)

    try:
        test_app = create_app(
            test_settings,
            test_engine,
            unused_uow_factory,
            NoopScheduleCache(),
        )
        assert test_app.title == test_app_name
        assert test_app.state.engine is test_engine
    finally:
        await test_engine.dispose()
