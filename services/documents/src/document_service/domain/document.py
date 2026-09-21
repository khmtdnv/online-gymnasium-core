from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID


class DocumentStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class DocumentJob:
    id: UUID
    document_type: str
    status: DocumentStatus
    object_key: str | None
    error_message: str | None
    created_at: datetime
