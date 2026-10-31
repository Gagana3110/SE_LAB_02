from datetime import UTC, date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

QUEUED = "QUEUED"
RUNNING = "RUNNING"
DONE = "DONE"
FAILED = "FAILED"


class ForecastRun(Base):
    __tablename__ = "forecast_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(10), default=QUEUED, index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    horizon: Mapped[int]
    granularity: Mapped[str] = mapped_column(String(5))
    allowed_models: Mapped[list] = mapped_column(JSON)
    product_ids: Mapped[list] = mapped_column(JSON)
    skipped: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ForecastLine(Base):
    __tablename__ = "forecast_lines"
    __table_args__ = (
        UniqueConstraint("run_id", "product_id", "period", name="uq_forecast_line"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("forecast_runs.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    period: Mapped[date] = mapped_column(Date)
    model: Mapped[str] = mapped_column(String(10))
    forecast: Mapped[float] = mapped_column(Float)
    lower80: Mapped[float] = mapped_column(Float)
    upper80: Mapped[float] = mapped_column(Float)
    lower95: Mapped[float] = mapped_column(Float)
    upper95: Mapped[float] = mapped_column(Float)
