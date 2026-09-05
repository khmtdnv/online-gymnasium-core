from fastapi import APIRouter

from schedule_service.api.health import router as health_router

router = APIRouter()

router.include_router(health_router)
