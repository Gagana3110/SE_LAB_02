from datetime import UTC, date, datetime

from sqlalchemy import JSON, CheckConstraint, Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SalesRecord(Base):
    __tablename__ = "sales_history"
    __table_args__ = (
        UniqueConstraint("product_id", "period", "region", name="uq_sales_product_period_region"),
        CheckConstraint("quantity >= 0", name="ck_sales_quantity_not_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    period: Mapped[date] = mapped_column(Date, index=True)
    quantity: Mapped[int]
    # Empty rather than NULL, because NULLs would not count as duplicates in the unique rule.
    region: Mapped[str] = mapped_column(String(60), default="")


class ImportRun(Base):
    """One uploaded file: who sent it, the result, and the rows rejected for the error report."""

    __tablename__ = "import_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    filename: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    imported: Mapped[int]
    updated: Mapped[int]
    rejected: Mapped[int]
    errors: Mapped[list] = mapped_column(JSON)
