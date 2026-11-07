
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Alert(Base):
    """Inventory and forecast alerts with active-alert deduplication."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)

    alert_type: Mapped[str] = mapped_column(String(40), index=True)
    entity_type: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[int] = mapped_column(index=True)

    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)

    current_value: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    threshold_value: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )

    is_open: Mapped[bool] = mapped_column(default=True, index=True)

    active_key: Mapped[str | None] = mapped_column(
        String(150), unique=True, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
