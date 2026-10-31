from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class _Item:
    """Fields shared by products and raw materials (DFS-F-004). Items are deactivated, not deleted,
    so that sales history and past forecasts keep pointing at them."""

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    unit: Mapped[str] = mapped_column(String(20))
    category: Mapped[str | None] = mapped_column(String(60), nullable=True)
    active: Mapped[bool] = mapped_column(default=True, index=True)


class Product(_Item, Base):
    __tablename__ = "products"

    bom_lines: Mapped[list["BomLine"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", order_by="BomLine.id"
    )


class RawMaterial(_Item, Base):
    __tablename__ = "raw_materials"


class BomLine(Base):
    """Quantity of one raw material needed to make one unit of a product."""

    __tablename__ = "bom_lines"
    __table_args__ = (
        UniqueConstraint("product_id", "material_id", name="uq_bom_product_material"),
        CheckConstraint("qty_per_unit > 0", name="ck_bom_qty_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("raw_materials.id"), index=True)
    qty_per_unit: Mapped[Decimal] = mapped_column(Numeric(12, 4))

    product: Mapped[Product] = relationship(back_populates="bom_lines")
    material: Mapped[RawMaterial] = relationship()
