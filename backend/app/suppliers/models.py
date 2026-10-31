from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Supplier(Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        CheckConstraint("lead_time_days >= 1", name="ck_supplier_lead_time"),
        CheckConstraint("moq >= 1", name="ck_supplier_moq"),
        CheckConstraint("unit_price > 0", name="ck_supplier_price"),
        CheckConstraint("monthly_capacity >= 1", name="ck_supplier_capacity"),
        CheckConstraint("reliability_pct BETWEEN 0 AND 100", name="ck_supplier_reliability"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    lead_time_days: Mapped[int]
    moq: Mapped[int]
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    monthly_capacity: Mapped[int]
    reliability_pct: Mapped[int]
    active: Mapped[bool] = mapped_column(default=True, index=True)


class MaterialSupplier(Base):
    """An approved supplier of a raw material (DFS-F-006)."""

    __tablename__ = "material_suppliers"
    __table_args__ = (
        UniqueConstraint("material_id", "supplier_id", name="uq_material_supplier"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("raw_materials.id"), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    preferred: Mapped[bool] = mapped_column(default=False)

    supplier: Mapped[Supplier] = relationship()
