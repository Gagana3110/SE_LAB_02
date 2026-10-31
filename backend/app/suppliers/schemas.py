from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.masterdata.schemas import Code, ItemOut, Name

MAX_INT = 2_147_483_647
LeadTime = Annotated[int, Field(ge=1, le=3650)]
Moq = Annotated[int, Field(ge=1, le=MAX_INT)]
Price = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
Capacity = Annotated[int, Field(ge=1, le=MAX_INT)]
Reliability = Annotated[int, Field(ge=0, le=100)]


class SupplierCreate(BaseModel):
    code: Code
    name: Name
    lead_time_days: LeadTime
    moq: Moq
    unit_price: Price
    monthly_capacity: Capacity
    reliability_pct: Reliability


class SupplierUpdate(BaseModel):
    """Only the fields sent are changed. Send active=false to deactivate."""

    code: Code | None = None
    name: Name | None = None
    lead_time_days: LeadTime | None = None
    moq: Moq | None = None
    unit_price: Price | None = None
    monthly_capacity: Capacity | None = None
    reliability_pct: Reliability | None = None
    active: bool | None = None

    @model_validator(mode="after")
    def fields_cannot_be_cleared(self):
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be empty")
        return self


class SupplierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    lead_time_days: int
    moq: int
    unit_price: float
    monthly_capacity: int
    reliability_pct: int
    active: bool


class LinkIn(BaseModel):
    supplier_id: int
    preferred: bool = False


class LinksUpdate(BaseModel):
    links: list[LinkIn]

    @model_validator(mode="after")
    def links_are_consistent(self):
        ids = [link.supplier_id for link in self.links]
        if len(ids) != len(set(ids)):
            raise ValueError("A supplier can be linked only once")
        if self.links and sum(link.preferred for link in self.links) != 1:
            raise ValueError("Exactly one supplier must be preferred")
        return self


class LinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    supplier: SupplierOut
    preferred: bool


class MaterialGap(ItemOut):
    """A raw material that cannot be purchased yet, because no active supplier is linked."""
