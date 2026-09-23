from fastapi import APIRouter

router = APIRouter()


@router.get("/health/live")
def health_live() -> dict[str, str]:
    return {"status": "ok"}
