
"""Request and response shapes for forecasting."""

from datetime import date, datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel

from app.forecasting.engine import MONTH, WEEK

HORIZON_LIMITS = {
    MONTH: (1, 12),
    WEEK: (4, 52),
}


class _Camel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class RunCreate(_Camel):
    product_ids: list[int] | Literal["ALL"] = Field(min_length=1)
    horizon: int
    granularity: Literal["MONTH", "WEEK"] = MONTH
    models: list[Literal["MA", "HW", "SARIMAX"]] = Field(
        default=["MA", "HW", "SARIMAX"],
        min_length=1,
    )

    @model_validator(mode="after")
    def horizon_fits_granularity(self):
        low, high = HORIZON_LIMITS[self.granularity]

        if not low <= self.horizon <= high:
            raise ValueError(
                f"Horizon must be {low} to {high} for {self.granularity}"
            )

        return self


class RunAccepted(_Camel):
    run_id: int
    status: str


class PointOut(_Camel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )

    period: date
    forecast: float
    lower80: float
    upper80: float
    lower95: float
    upper95: float


class ForecastMetricsOut(_Camel):
    mape: float | None
    mae: float | None
    bias: float | None
    confidence: str


class ProductForecast(_Camel):
    product_id: int
    code: str
    model: str
    points: list[PointOut]
    metrics: ForecastMetricsOut | None = None


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


class RunSummary(_Camel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )

    run_id: int = Field(validation_alias="id")
    status: str
    horizon: int
    granularity: str
    created_at: datetime


class ActualOut(_Camel):
    period: date
    actual: float


class ProductChart(ProductForecast):
    """Actual-vs-forecast chart data."""

    history: list[ActualOut]


class ForecastOverrideCreate(_Camel):
    product_id: int = Field(gt=0)
    period: date
    new_forecast: float = Field(ge=0, allow_inf_nan=False)
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("An override reason is required")

        return value


class ForecastOverrideOut(_Camel):
    id: int
    run_id: int
    product_id: int
    period: date
    old_value: float
    new_value: float
    reason: str
    user_id: int
    created_at: datetime

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class ForecastApprovalOut(_Camel):
    id: int
    run_id: int
    approved_by: int
    approved_at: datetime

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class AuditLogOut(_Camel):
    id: int
    user_id: int
    timestamp: datetime
    action: str
    run_id: int
    product_id: int | None
    period: date | None
    old_value: float | None
    new_value: float | None
    reason: str | None

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )
