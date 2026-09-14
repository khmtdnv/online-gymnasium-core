import redis.asyncio as redis

from schedule_service.app import create_app
from schedule_service.config import Settings
from schedule_service.infrastructure.database import (
    create_engine,
    create_session_factory,
)
from schedule_service.infrastructure.redis_schedule_cache import RedisScheduleCache
from schedule_service.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

settings = Settings()
engine = create_engine(settings.database_url)
session_factory = create_session_factory(engine)
redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
schedule_cache = RedisScheduleCache(redis_client)

app = create_app(
    settings=settings,
    engine=engine,
    uow_factory=lambda: SqlAlchemyUnitOfWork(session_factory),
    schedule_cache=schedule_cache,
)
