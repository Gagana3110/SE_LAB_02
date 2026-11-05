"""Pure, deterministic calculations for BOM explosion and inventory planning."""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable, Mapping


SERVICE_LEVEL_Z = {90: Decimal("1.28"), 95: Decimal("1.65")}


def _decimal(value: Decimal | int | float | str, field: str) -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field} must be a valid number") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def _non_negative(value: Decimal | int | float | str, field: str) -> Decimal:
    result = _decimal(value, field)
    if result < 0:
        raise ValueError(f"{field} cannot be negative")
    return result


def gross_requirement(approved_forecast: Decimal | int | float | str,
                       bom_quantity: Decimal | int | float | str) -> Decimal:
    """Material gross need for one product: approved forecast × BOM quantity."""
    forecast = _non_negative(approved_forecast, "approved_forecast")
    quantity = _non_negative(bom_quantity, "bom_quantity")
    return forecast * quantity


def net_requirement(gross: Decimal | int | float | str,
                    on_hand: Decimal | int | float | str,
                    open_orders: Decimal | int | float | str = 0) -> Decimal:
    """Need remaining after stock and open orders; never return a negative need."""
    gross_qty = _non_negative(gross, "gross")
    stock = _non_negative(on_hand, "on_hand")
    ordered = _non_negative(open_orders, "open_orders")
    return max(Decimal("0"), gross_qty - stock - ordered)


def safety_stock(sigma_daily_demand: Decimal | int | float | str,
                 lead_time_days: Decimal | int | float | str,
                 service_level: int = 95) -> Decimal:
    """Safety stock = z × population/sample demand sigma × sqrt(lead time)."""
    if service_level not in SERVICE_LEVEL_Z:
        raise ValueError("service_level must be 90 or 95")
    sigma = _non_negative(sigma_daily_demand, "sigma_daily_demand")
    lead_time = _non_negative(lead_time_days, "lead_time_days")
    return SERVICE_LEVEL_Z[service_level] * sigma * lead_time.sqrt()


def reorder_point(avg_daily_demand: Decimal | int | float | str,
                  lead_time_days: Decimal | int | float | str,
                  safety_stock_qty: Decimal | int | float | str) -> Decimal:
    """Reorder point = average daily demand × lead time + safety stock."""
    average = _non_negative(avg_daily_demand, "avg_daily_demand")
    lead_time = _non_negative(lead_time_days, "lead_time_days")
    buffer = _non_negative(safety_stock_qty, "safety_stock_qty")
    return average * lead_time + buffer


@dataclass(frozen=True)
class BomComponent:
    product_id: int
    material_id: int
    qty_per_unit: Decimal | int | float | str


def explode_bom_requirements(
    approved_forecasts: Mapping[int, Decimal | int | float | str],
    bom_lines: Iterable[BomComponent],
) -> dict[int, Decimal]:
    """Aggregate gross material requirements across all forecast products."""
    totals: dict[int, Decimal] = defaultdict(Decimal)
    for line in bom_lines:
        if line.product_id not in approved_forecasts:
            continue
        totals[line.material_id] += gross_requirement(
            approved_forecasts[line.product_id], line.qty_per_unit
        )
    return dict(sorted(totals.items()))
