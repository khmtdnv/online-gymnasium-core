from datetime import date
from typing import Protocol

from analytics_service.application.workload import ClassDailyWorkload


class WorkloadRepository(Protocol):
    async def get(self, *, class_id: int, day: date) -> ClassDailyWorkload | None: ...
