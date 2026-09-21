from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID as PSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from document_service.infrastructure.models.base import Base


class DocumentTaskOutboxRow(Base):
    __tablename__ = "document_task_outbox"

    id: Mapped[UUID] = mapped_column(
        PSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    document_job_id: Mapped[UUID] = mapped_column(
        PSQLUUID(as_uuid=True),
        ForeignKey("document_jobs.id"),
        unique=True,
        nullable=False,
    )

    task_name: Mapped[str] = mapped_column(
        String,
        server_default="documents.generate_certificate",
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        Index(
            "document_task_outbox_unpublished_created_at_idx",
            "created_at",
            postgresql_where=text("published_at IS NULL"),
        ),
    )
