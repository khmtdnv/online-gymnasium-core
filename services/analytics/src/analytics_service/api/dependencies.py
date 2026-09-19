from fastapi import Request

from analytics_service.application.ports.workload_repository import WorkloadRepository


def get_workload_repository(request: Request) -> WorkloadRepository:
    return request.app.state.workload_repository_factory()
