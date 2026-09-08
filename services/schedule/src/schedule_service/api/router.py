from fastapi import APIRouter

from schedule_service.api.health import router as health_router
from schedule_service.api.lessons import router as lessons_router

router = APIRouter()

router.include_router(health_router)
router.include_router(lessons_router)
