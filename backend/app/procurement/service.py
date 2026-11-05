"""Small orchestration helpers for the DFS-18 planning calculations."""

from dataclasses import dataclass
from decimal import Decimal

from app.procurement.calculations import net_requirement, reorder_point, safety_stock


@dataclass(frozen=True)
class MaterialPlan:
    gross_requirement: Decimal
    net_requirement: Decimal
    safety_stock: Decimal
    reorder_point: Decimal


def calculate_material_plan(
    *,
    gross: Decimal | int | float | str,
    on_hand: Decimal | int | float | str,
    open_orders: Decimal | int | float | str,
    avg_daily_demand: Decimal | int | float | str,
    sigma_daily_demand: Decimal | int | float | str,
    lead_time_days: Decimal | int | float | str,
    service_level: int = 95,
) -> MaterialPlan:
    """Calculate net need, safety stock and ROP for one material."""
    from app.procurement.calculations import _non_negative

    gross_qty = _non_negative(gross, "gross")
    safety = safety_stock(sigma_daily_demand, lead_time_days, service_level)
    return MaterialPlan(
        gross_requirement=gross_qty,
        net_requirement=net_requirement(gross_qty, on_hand, open_orders),
        safety_stock=safety,
        reorder_point=reorder_point(avg_daily_demand, lead_time_days, safety),
    )
