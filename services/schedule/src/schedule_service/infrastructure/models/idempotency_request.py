from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from schedule_service.infrastructure.models.base import Base


class IdempotencyRequestRow(Base):
    __tablename__ = "idempotency_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation: Mapped[str] = mapped_column(String, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String, nullable=False)
    request_hash: Mapped[str] = mapped_column(String, nullable=False)
    lesson_id: Mapped[int | None] = mapped_column(ForeignKey("scheduled_lessons.id"), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "operation",
            "idempotency_key",
            name="idempotency_requests_operation_key_unique",
        ),
    )
