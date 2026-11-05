from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ItemType = Literal["product", "raw_material"]
MovementType = Literal["receipt", "issue", "adjustment"]
MovementQuantity = Annotated[Decimal, Field(max_digits=14, decimal_places=4)]
PriceChange = Annotated[Decimal, Field(ge=-100, le=10000, max_digits=9, decimal_places=4)]
TrendIndex = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=4)]


class StockMovementCreate(BaseModel):
    item_type: ItemType
    item_id: int = Field(gt=0)
    movement_type: MovementType
    qty: MovementQuantity
    movement_date: date
    reference: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def quantity_matches_movement(self):
        if self.movement_type in {"receipt", "issue"} and self.qty <= 0:
            raise ValueError("Receipt and issue quantities must be greater than zero")
        if self.movement_type == "adjustment" and self.qty == 0:
            raise ValueError("Adjustment quantity cannot be zero")
        return self


class StockMovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_type: str
    item_id: int
    movement_type: str
    qty: MovementQuantity
    movement_date: date
    reference: str | None


class StockBalanceOut(BaseModel):
    item_type: str
    item_id: int
    code: str
    name: str
    unit: str
    on_hand_qty: Decimal


class MarketIndicatorCreate(BaseModel):
    product_id: int = Field(gt=0)
    period: date
    promotion: bool = False
    price_change_pct: PriceChange = Decimal("0")
    holiday_flag: bool = False
    trend_index: TrendIndex = Decimal("0")


class MarketIndicatorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    period: date
    promotion: bool
    price_change_pct: Decimal
    holiday_flag: bool
    trend_index: Decimal
