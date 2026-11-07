
import logging
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.alerts.models import Alert
from app.auth.models import Role, User
from app.config import settings
from app.forecasting.models import (
    DONE,
    ForecastLine,
    ForecastMetric,
    ForecastRun,
)
from app.inventory.models import StockMovement
from app.masterdata.models import BomLine, Product, RawMaterial
from app.notifications.email import send_email
from app.procurement.calculations import reorder_point
from app.suppliers.models import MaterialSupplier, Supplier

log = logging.getLogger(__name__)

REORDER = "REORDER_POINT"
STOCKOUT = "LEAD_TIME_STOCKOUT"
MAPE = "HIGH_MAPE"


def _stock(db: Session, material_id: int) -> float:
    movements = db.scalars(
        select(StockMovement).where(
            StockMovement.item_type == "raw_material",
            StockMovement.item_id == material_id,
        )
    )
    balance = 0.0
    for movement in movements:
        qty = float(movement.qty)
        if movement.movement_type == "receipt":
            balance += qty
        elif movement.movement_type == "issue":
            balance -= qty
        else:
            balance += qty
    return balance


def _active_supplier(db: Session, material_id: int):
    rows = db.execute(
        select(Supplier.lead_time_days)
        .join(MaterialSupplier, MaterialSupplier.supplier_id == Supplier.id)
        .where(
            MaterialSupplier.material_id == material_id,
            Supplier.active.is_(True),
        )
        .order_by(MaterialSupplier.preferred.desc(), Supplier.lead_time_days)
    )
    return rows.first()


def _latest_run(db: Session):
    return db.scalar(
        select(ForecastRun)
        .where(ForecastRun.status == DONE)
        .order_by(ForecastRun.id.desc())
    )


def _forecast_material_demand(
    db: Session,
    run: ForecastRun,
    material_id: int,
) -> list[tuple[date, float]]:
    rows = db.execute(
        select(ForecastLine.period, ForecastLine.product_id, ForecastLine.forecast)
        .where(ForecastLine.run_id == run.id)
        .order_by(ForecastLine.period)
    )

    bom_rows = db.execute(
        select(BomLine.product_id, BomLine.qty_per_unit)
        .where(BomLine.material_id == material_id)
    )
    bom = {product_id: float(qty) for product_id, qty in bom_rows}

    demand_by_period: dict[date, float] = {}
    for period, product_id, forecast in rows:
        if product_id in bom:
            demand_by_period[period] = demand_by_period.get(period, 0.0) + (
                max(float(forecast), 0.0) * bom[product_id]
            )

    return sorted(demand_by_period.items())


def _period_days(run: ForecastRun) -> int:
    return 7 if run.granularity.lower().startswith("w") else 30


def _create_alert(
    db: Session,
    *,
    alert_type: str,
    entity_type: str,
    entity_id: int,
    title: str,
    message: str,
    current_value: float | None = None,
    threshold_value: float | None = None,
) -> Alert | None:
    key = f"{alert_type}:{entity_type}:{entity_id}"
    existing = db.scalar(
        select(Alert).where(
            Alert.active_key == key,
            Alert.is_open.is_(True),
        )
    )
    if existing:
        return None

    alert = Alert(
        alert_type=alert_type,
        entity_type=entity_type,
        entity_id=entity_id,
        title=title,
        message=message,
        current_value=current_value,
        threshold_value=threshold_value,
        is_open=True,
        active_key=key,
    )
    db.add(alert)

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return None

    return alert


def _notify_inventory_managers(db: Session, alert: Alert) -> None:
    users = db.scalars(
        select(User).where(User.role == Role.INVENTORY_MANAGER)
    )
    sent = False

    for user in users:
        try:
            send_email(
                user.email,
                f"DFS Alert: {alert.title}",
                alert.message,
            )
            sent = True
        except OSError:
            log.exception("Could not email alert %s to %s", alert.id, user.email)

    if sent:
        alert.notified_at = datetime.now(UTC)


def evaluate_material_alerts(db: Session) -> int:
    run = _latest_run(db)
    if run is None:
        return 0

    created = 0
    materials = db.scalars(
        select(RawMaterial).where(RawMaterial.active.is_(True))
    )

    for material in materials:
        supplier = _active_supplier(db, material.id)
        if supplier is None:
            continue

        lead_time = int(supplier.lead_time_days)
        stock = _stock(db, material.id)
        demand = _forecast_material_demand(db, run, material.id)

        if not demand:
            continue

        period_days = _period_days(run)
        total_demand = sum(quantity for _, quantity in demand)
        avg_daily_demand = total_demand / (len(demand) * period_days)

        # DFS-18 safety stock is not estimated here because the forecast
        # does not provide daily demand variance.
        point = float(reorder_point(avg_daily_demand, lead_time, 0))

        if stock < point:
            alert = _create_alert(
                db,
                alert_type=REORDER,
                entity_type="raw_material",
                entity_id=material.id,
                title=f"Low stock: {material.name}",
                message=(
                    f"{material.name} stock is {stock:.2f}, below its "
                    f"calculated reorder point of {point:.2f}."
                ),
                current_value=stock,
                threshold_value=point,
            )
            if alert:
                db.flush()
                _notify_inventory_managers(db, alert)
                created += 1

        lead_demand = 0.0
        deadline = date.today() + timedelta(days=lead_time)
        for period, quantity in demand:
            if period <= deadline:
                lead_demand += quantity

        if stock - lead_demand <= 0:
            alert = _create_alert(
                db,
                alert_type=STOCKOUT,
                entity_type="raw_material",
                entity_id=material.id,
                title=f"Projected stock-out: {material.name}",
                message=(
                    f"{material.name} is projected to run out within "
                    f"{lead_time} supplier lead-time days. Current stock: "
                    f"{stock:.2f}; projected lead-time demand: {lead_demand:.2f}."
                ),
                current_value=stock,
                threshold_value=lead_demand,
            )
            if alert:
                db.flush()
                _notify_inventory_managers(db, alert)
                created += 1

    db.commit()
    return created


def evaluate_mape_alerts(db: Session) -> int:
    run = _latest_run(db)
    if run is None:
        return 0

    created = 0
    metrics = db.scalars(
        select(ForecastMetric).where(ForecastMetric.run_id == run.id)
    )

    for metric in metrics:
        if metric.mape is None or metric.mape <= settings.mape_alert_threshold:
            continue

        product = db.get(Product, metric.product_id)
        if product is None:
            continue

        alert = _create_alert(
            db,
            alert_type=MAPE,
            entity_type="product",
            entity_id=product.id,
            title=f"Forecast accuracy alert: {product.name}",
            message=(
                f"{product.name} has MAPE {metric.mape:.2f}%, exceeding "
                f"the configured threshold of {settings.mape_alert_threshold:.2f}%."
            ),
            current_value=metric.mape,
            threshold_value=settings.mape_alert_threshold,
        )
        if alert:
            db.flush()
            _notify_inventory_managers(db, alert)
            created += 1

    db.commit()
    return created


def evaluate_all_alerts(db: Session) -> int:
    return evaluate_material_alerts(db) + evaluate_mape_alerts(db)


def list_open_alerts(db: Session) -> list[Alert]:
    return list(
        db.scalars(
            select(Alert)
            .where(Alert.is_open.is_(True))
            .order_by(Alert.created_at.desc(), Alert.id.desc())
        )
    )
