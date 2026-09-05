from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from schedule_service.api.router import router
from schedule_service.config import Settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        yield
    finally:
        await app.state.engine.dispose()


def create_app(settings: Settings, engine: AsyncEngine) -> FastAPI:

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.include_router(router)
    app.state.engine = engine

    return app
