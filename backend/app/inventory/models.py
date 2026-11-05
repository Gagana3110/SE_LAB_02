from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class StockMovement(Base):
    """An immutable receipt, issue or signed stock adjustment for an item."""

    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_type: Mapped[str] = mapped_column(String(20), index=True)
    item_id: Mapped[int] = mapped_column(index=True)
    movement_type: Mapped[str] = mapped_column(String(20), index=True)
    qty: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    movement_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)


class MarketIndicator(Base):
    """Market context recorded for one product and demand period."""

    __tablename__ = "market_indicators"
    __table_args__ = (
        UniqueConstraint("product_id", "period", name="uq_market_indicator_product_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    period: Mapped[date] = mapped_column(Date, index=True)
    promotion: Mapped[bool] = mapped_column(Boolean, default=False)
    price_change_pct: Mapped[Decimal] = mapped_column(Numeric(9, 4), default=Decimal("0"))
    holiday_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    trend_index: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"))
