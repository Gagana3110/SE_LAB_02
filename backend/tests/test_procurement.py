from decimal import Decimal

import pytest

from app.procurement.calculations import (
    BomComponent,
    explode_bom_requirements,
    gross_requirement,
    net_requirement,
    reorder_point,
    safety_stock,
)
from app.procurement.service import calculate_material_plan

D = Decimal


def test_gross_requirement_matches_hand_calculation():
    # 120 finished units × 2.5 kg of material per unit = 300 kg.
    assert gross_requirement(D("120"), D("2.5")) == D("300.0")


def test_bom_explosion_aggregates_same_material_across_products():
    # Product 1: 100 × 2 = 200; Product 2: 40 × 3 = 120; total = 320.
    forecasts = {1: D("100"), 2: D("40")}
    bom = [BomComponent(1, 10, D("2")), BomComponent(2, 10, D("3"))]
    assert explode_bom_requirements(forecasts, bom) == {10: D("320")}


def test_bom_explosion_ignores_products_without_an_approved_forecast():
    forecasts = {1: D("100")}
    bom = [BomComponent(1, 10, D("2")), BomComponent(2, 10, D("3"))]
    assert explode_bom_requirements(forecasts, bom) == {10: D("200")}


def test_net_requirement_subtracts_on_hand_and_open_orders():
    # 300 gross - 80 available - 50 on order = 170 to buy.
    assert net_requirement(D("300"), D("80"), D("50")) == D("170")


def test_net_requirement_never_goes_below_zero():
    assert net_requirement(D("100"), D("120"), D("10")) == D("0")


@pytest.mark.parametrize(
    ("sigma", "lead_time", "expected_95", "expected_90"),
    [
        (D("4"), D("9"), D("19.80"), D("15.36")),
        (D("2"), D("5"), D("7.379024325749306"), D("5.724334022399462")),
        (D("6"), D("4"), D("19.80"), D("15.36")),
    ],
)
def test_safety_stock_for_three_materials_at_both_service_levels(
    sigma, lead_time, expected_95, expected_90
):
    assert safety_stock(sigma, lead_time, 95) == pytest.approx(expected_95)
    assert safety_stock(sigma, lead_time, 90) == pytest.approx(expected_90)


def test_reorder_point_matches_hand_calculation():
    # Average use 12/day × 5 days + 7.379... safety stock.
    stock_buffer = safety_stock(D("2"), D("5"), 95)
    assert reorder_point(D("12"), D("5"), stock_buffer) == D("60") + stock_buffer


def test_material_plan_calculates_all_four_outputs():
    plan = calculate_material_plan(
        gross=D("300"), on_hand=D("80"), open_orders=D("50"),
        avg_daily_demand=D("12"), sigma_daily_demand=D("2"),
        lead_time_days=D("5"), service_level=95,
    )
    assert plan.gross_requirement == D("300")
    assert plan.net_requirement == D("170")
    assert plan.safety_stock == safety_stock(D("2"), D("5"), 95)
    assert plan.reorder_point == D("60") + plan.safety_stock


@pytest.mark.parametrize(
    "call",
    [
        lambda: gross_requirement(-1, 2),
        lambda: gross_requirement(1, -2),
        lambda: net_requirement(10, -1, 0),
        lambda: safety_stock(1, -1, 95),
        lambda: safety_stock(1, 5, 99),
        lambda: reorder_point(1, 5, -1),
    ],
)
def test_invalid_negative_values_and_service_level_are_rejected(call):
    with pytest.raises(ValueError):
        call()
