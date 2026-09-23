from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class PendingDocumentTask:
    id: UUID
    document_job_id: UUID
    task_name: str
    created_at: datetime


class DocumentTaskOutboxRepository(Protocol):
    def get_pending(self, *, limit: int) -> list[PendingDocumentTask]: ...

    def mark_published(self, *, task_id: UUID) -> None: ...
