from collections.abc import Callable
from datetime import date
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query

from analytics_service.api.dependencies import get_workload_repository
from analytics_service.application.ports.workload_repository import WorkloadRepository
from analytics_service.application.workload import ClassDailyWorkload


def create_app(repository_factory: Callable[[], WorkloadRepository]) -> FastAPI:
    app = FastAPI()
    app.state.workload_repository_factory = repository_factory

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/workload")
    async def get_workload(
        class_id: Annotated[int, Query(gt=0)],
        day: date,
        repository: Annotated[WorkloadRepository, Depends(get_workload_repository)],
    ) -> ClassDailyWorkload:
        try:
            workload = await repository.get(
                class_id=class_id,
                day=day,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail="Analytics storage is unavailable",
            ) from exc

        if workload is None:
            raise HTTPException(
                status_code=404,
                detail="Workload was not found",
            )

        return workload

    return app
