from fastapi import APIRouter

from gateway_service.api.auth import router as auth_router
from gateway_service.api.backoffice import router as backoffice_router
from gateway_service.api.health import router as health_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(health_router)
router.include_router(backoffice_router)
