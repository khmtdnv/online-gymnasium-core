from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from document_service.infrastructure.models.base import Base


class DocumentJobRow(Base):
    __tablename__ = "document_jobs"

    id: Mapped[UUID] = mapped_column(
        PSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    document_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        server_default="pending",
    )

    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    object_key: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="document_jobs_valid_status",
        ),
    )
