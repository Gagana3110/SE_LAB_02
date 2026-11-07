
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest

from app.alerts import service
from app.alerts.models import Alert
from app.auth.models import Role
from app.forecasting.models import (
    DONE,
    ForecastLine,
    ForecastMetric,
    ForecastRun,
)
from app.inventory.models import StockMovement
from app.masterdata.models import BomLine, Product, RawMaterial
from app.suppliers.models import MaterialSupplier, Supplier


@pytest.fixture
def product(db):
    item = Product(code="P-ALERT", name="Alert Widget", unit="each")
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@pytest.fixture
def material(db):
    item = RawMaterial(code="M-ALERT", name="Alert Steel", unit="kg")
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def create_forecast_run(db, planner, product, forecast=70.0):
    run = ForecastRun(
        status=DONE,
        created_by=planner.id,
        horizon=1,
        granularity="weekly",
        allowed_models=["SARIMAX"],
        product_ids=[product.id],
    )
    db.add(run)
    db.flush()

    db.add(
        ForecastLine(
            run_id=run.id,
            product_id=product.id,
            period=date.today(),
            model="SARIMAX",
            forecast=forecast,
            lower80=forecast * 0.8,
            upper80=forecast * 1.2,
            lower95=forecast * 0.7,
            upper95=forecast * 1.3,
        )
    )
    db.commit()
    db.refresh(run)
    return run


def create_material_setup(db, material, product, lead_time=7):
    db.add(
        BomLine(
            product_id=product.id,
            material_id=material.id,
            qty_per_unit=Decimal("1.0000"),
        )
    )

    supplier = Supplier(
        code="SUP-ALERT-01",
        name="Alert Test Supplier",
        lead_time_days=lead_time,
        moq=1,
        unit_price=Decimal("10.00"),
        monthly_capacity=1000,
        reliability_pct=95,
        active=True,
    )
    db.add(supplier)
    db.flush()

    db.add(
        MaterialSupplier(
            material_id=material.id,
            supplier_id=supplier.id,
            preferred=True,
        )
    )
    db.commit()


def add_stock(db, material, quantity):
    db.add(
        StockMovement(
            item_type="raw_material",
            item_id=material.id,
            movement_type="receipt",
            qty=Decimal(str(quantity)),
            movement_date=date.today(),
        )
    )
    db.commit()


def test_low_stock_and_lead_time_stockout_alerts(
    db, make_user, material, product
):
    planner = make_user(Role.DEMAND_PLANNER)
    make_user(Role.INVENTORY_MANAGER)

    create_forecast_run(db, planner, product, forecast=70)
    create_material_setup(db, material, product, lead_time=7)
    add_stock(db, material, 1)

    with patch("app.alerts.service.send_email") as mock_email:
        created = service.evaluate_material_alerts(db)

    alerts = db.query(Alert).filter(Alert.is_open.is_(True)).all()
    alert_types = {alert.alert_type for alert in alerts}

    assert created == 2
    assert service.REORDER in alert_types
    assert service.STOCKOUT in alert_types
    assert mock_email.call_count == 2
    assert all(alert.entity_id == material.id for alert in alerts)


def test_material_alerts_are_not_duplicated(
    db, make_user, material, product
):
    planner = make_user(Role.DEMAND_PLANNER)
    make_user(Role.INVENTORY_MANAGER)

    create_forecast_run(db, planner, product, forecast=70)
    create_material_setup(db, material, product, lead_time=7)
    add_stock(db, material, 1)

    with patch("app.alerts.service.send_email"):
        first_count = service.evaluate_material_alerts(db)
        second_count = service.evaluate_material_alerts(db)

    alerts = db.query(Alert).filter(Alert.is_open.is_(True)).all()

    assert first_count == 2
    assert second_count == 0
    assert len(alerts) == 2


def test_high_mape_creates_alert_and_sends_email(
    db, make_user, product
):
    planner = make_user(Role.DEMAND_PLANNER)
    make_user(Role.INVENTORY_MANAGER)

    run = create_forecast_run(db, planner, product)

    db.add(
        ForecastMetric(
            run_id=run.id,
            product_id=product.id,
            model="SARIMAX",
            mape=25.0,
            mae=10.0,
            bias=0.5,
            confidence="HIGH",
        )
    )
    db.commit()

    with patch("app.alerts.service.send_email") as mock_email:
        created = service.evaluate_mape_alerts(db)

    alert = db.query(Alert).filter_by(
        alert_type=service.MAPE,
        entity_id=product.id,
    ).first()

    assert created == 1
    assert alert is not None
    assert alert.current_value == 25.0
    assert alert.threshold_value == service.settings.mape_alert_threshold
    mock_email.assert_called_once()


def test_mape_below_threshold_does_not_create_alert(
    db, make_user, product
):
    planner = make_user(Role.DEMAND_PLANNER)

    run = create_forecast_run(db, planner, product)

    db.add(
        ForecastMetric(
            run_id=run.id,
            product_id=product.id,
            model="SARIMAX",
            mape=10.0,
            mae=5.0,
            bias=0.2,
            confidence="HIGH",
        )
    )
    db.commit()

    created = service.evaluate_mape_alerts(db)

    assert created == 0
    assert db.query(Alert).count() == 0


def test_alert_dashboard_requires_login(client):
    response = client.get("/api/alerts")
    assert response.status_code == 401


def test_inventory_manager_can_view_alert_dashboard(
    client, login_as
):
    login_as(Role.INVENTORY_MANAGER)

    response = client.get("/api/alerts")

    assert response.status_code == 200
    assert response.json() == []
