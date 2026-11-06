from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class PurchaseRecommendation(Base):
    __tablename__ = "purchase_recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)

    forecast_run_id: Mapped[int] = mapped_column(
        ForeignKey("forecast_runs.id"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default="PENDING", index=True
    )

    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    decided_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    lines: Mapped[list["RecommendationLine"]] = relationship(
        back_populates="recommendation",
        cascade="all, delete-orphan",
    )


class RecommendationLine(Base):
    __tablename__ = "recommendation_lines"

    id: Mapped[int] = mapped_column(primary_key=True)

    recommendation_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_recommendations.id"), index=True
    )
    material_id: Mapped[int] = mapped_column(
        ForeignKey("raw_materials.id"), index=True
    )

    need_date: Mapped[date] = mapped_column(Date)

    net_requirement: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    total_order_qty: Mapped[Decimal] = mapped_column(Numeric(14, 4))

    status: Mapped[str] = mapped_column(
        String(20), default="PENDING", index=True
    )
    rejection_comment: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    recommendation: Mapped["PurchaseRecommendation"] = relationship(
        back_populates="lines"
    )

    allocations: Mapped[list["SupplierAllocation"]] = relationship(
        back_populates="line",
        cascade="all, delete-orphan",
    )


class SupplierAllocation(Base):
    __tablename__ = "supplier_allocations"

    __table_args__ = (
        UniqueConstraint(
            "recommendation_line_id",
            "supplier_id",
            name="uq_recommendation_supplier",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    recommendation_line_id: Mapped[int] = mapped_column(
        ForeignKey("recommendation_lines.id"), index=True
    )
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id")
    )

    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    # Snapshot of supplier details used during recommendation generation.
    lead_time_days: Mapped[int]
    moq: Mapped[int]
    monthly_capacity: Mapped[int]
    reliability_pct: Mapped[int]
    preferred: Mapped[bool] = mapped_column(default=False)

    order_by_date: Mapped[date] = mapped_column(Date)

    line: Mapped["RecommendationLine"] = relationship(
        back_populates="allocations"
    )

    purchase_order: Mapped["PurchaseOrder | None"] = relationship(
        back_populates="allocation",
        uselist=False,
    )


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(primary_key=True)

    allocation_id: Mapped[int] = mapped_column(
        ForeignKey("supplier_allocations.id"),
        unique=True,
    )

    status: Mapped[str] = mapped_column(
        String(20), default="DRAFT", index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    allocation: Mapped["SupplierAllocation"] = relationship(
        back_populates="purchase_order"
    )
