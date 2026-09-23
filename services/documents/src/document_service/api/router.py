from fastapi import APIRouter

from document_service.api.documents import router as documents_router
from document_service.api.health import router as health_router

router = APIRouter()
router.include_router(health_router)
router.include_router(documents_router)
