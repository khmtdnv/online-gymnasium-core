from datetime import datetime

from sqlalchemy import Integer, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, VARCHAR
from sqlalchemy.orm import Mapped, mapped_column

from schedule_service.infrastructure.models.base import Base


class OutboxEventRow(Base):
    __tablename__ = "outbox_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(VARCHAR, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    published_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
