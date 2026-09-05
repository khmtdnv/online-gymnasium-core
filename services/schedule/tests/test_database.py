import pytest
from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.mark.anyio
async def test_db_engine() -> None:
    from schedule_service.infrastructure.database import create_engine

    test_url = "postgresql+asyncpg://schedule:password@localhost:5432/schedule"
    test_engine: AsyncEngine = create_engine(url=test_url)
    try:
        assert test_engine.url.render_as_string(hide_password=False) == test_url
    finally:
        await test_engine.dispose()
