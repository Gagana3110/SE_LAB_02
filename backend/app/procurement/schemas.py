from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class SupplierAllocationOut(CamelModel):
    id: int
    supplier_id: int
    quantity: Decimal
    unit_price: Decimal


class PurchaseOrderOut(CamelModel):
    id: int
    supplier_id: int
    quantity: Decimal
    unit_price: Decimal
    order_date: date
    status: str

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class RecommendationLineOut(CamelModel):
    id: int
    material_id: int
    need_date: date
    order_by_date: date
    net_requirement: Decimal
    total_order_qty: Decimal
    status: str
    rejection_comment: str | None = None
    allocations: list[SupplierAllocationOut] = Field(default_factory=list)
    purchase_orders: list[PurchaseOrderOut] = Field(default_factory=list)


class PurchaseRecommendationOut(CamelModel):
    id: int
    status: str
    created_at: datetime
    created_by: int
    lines: list[RecommendationLineOut] = Field(default_factory=list)


class RecommendationGenerateIn(CamelModel):
    need_date: date
    material_ids: list[int] | None = None


class RecommendationEditIn(CamelModel):
    total_order_qty: Decimal = Field(gt=0)


class RecommendationDecisionIn(CamelModel):
    decision: Literal["APPROVE", "REJECT"]
    comment: str | None = Field(default=None, max_length=2000)

    @field_validator("comment")
    @classmethod
    def clean_comment(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
        return value
