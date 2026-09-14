import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from schedule_service.infrastructure.database import create_engine


@pytest.mark.anyio
async def test_db_engine() -> None:

    test_url = "postgresql+asyncpg://schedule:password@localhost:5432/schedule"
    test_engine: AsyncEngine = create_engine(url=test_url)
    try:
        assert test_engine.url.render_as_string(hide_password=False) == test_url
    finally:
        await test_engine.dispose()


@pytest.mark.anyio
async def test_session_factory_creates_async_session() -> None:
    from schedule_service.infrastructure.database import create_session_factory

    engine = create_engine(
        url="postgresql+asyncpg://schedule:password@localhost:5432/schedule"
    )
    session_factory = create_session_factory(engine)
    session = session_factory()

    try:
        assert isinstance(session, AsyncSession)
        assert session.sync_session.expire_on_commit is False
    finally:
        await session.close()
        await engine.dispose()
