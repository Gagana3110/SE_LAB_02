"""Request and response shapes from the SAD (Section 4.3), which uses camelCase for this API."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from app.forecasting.engine import MONTH, WEEK

HORIZON_LIMITS = {MONTH: (1, 12), WEEK: (4, 52)}


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class RunCreate(_Camel):
    product_ids: list[int] | Literal["ALL"] = Field(min_length=1)
    horizon: int
    granularity: Literal["MONTH", "WEEK"] = MONTH
    models: list[Literal["MA", "HW"]] = Field(default=["MA", "HW"], min_length=1)

    @model_validator(mode="after")
    def horizon_fits_granularity(self):
        low, high = HORIZON_LIMITS[self.granularity]
        if not low <= self.horizon <= high:
            raise ValueError(f"Horizon must be {low} to {high} for {self.granularity}")
        return self


class RunAccepted(_Camel):
    run_id: int
    status: str


class PointOut(_Camel):
    period: date
    forecast: float
    lower80: float
    upper80: float
    lower95: float
    upper95: float


class ProductForecast(_Camel):
    product_id: int
    code: str
    model: str
    points: list[PointOut]


class SkippedProduct(_Camel):
    product_id: int
    reason: str


class RunOut(_Camel):
    run_id: int
    status: str
    horizon: int
    granularity: str
    error: str | None
    skipped: list[SkippedProduct]
    products: list[ProductForecast]


class ActualOut(_Camel):
    period: date
    actual: float


class ProductChart(ProductForecast):
    """Everything the actual-vs-forecast chart needs for one product (DFS-F-012)."""

    history: list[ActualOut]
