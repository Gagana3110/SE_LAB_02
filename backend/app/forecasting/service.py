import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.forecasting import engine
from app.forecasting.models import DONE, FAILED, QUEUED, RUNNING, ForecastLine, ForecastRun
from app.forecasting.schemas import RunCreate
from app.masterdata.models import Product
from app.sales.models import SalesRecord

logger = logging.getLogger(__name__)
# A run older than this lost its worker, so it should not block new runs forever.
STALE_AFTER = timedelta(minutes=30)
NO_HISTORY = "No sales history"


class UnknownProducts(Exception):
    pass


class RunInProgress(Exception):
    pass


def _resolve_products(db: Session, requested: list[int] | str) -> list[int]:
    active = set(db.scalars(select(Product.id).where(Product.active.is_(True))))
    if requested == "ALL":
        if not active:
            raise UnknownProducts([])
        return sorted(active)
    wanted = set(requested)
    if wanted - active:
        raise UnknownProducts(sorted(wanted - active))
    return sorted(wanted)


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)  # SQLite drops the timezone


def _overlaps_active_run(db: Session, product_ids: list[int]) -> bool:
    cutoff = datetime.now(UTC) - STALE_AFTER
    wanted = set(product_ids)
    active = db.scalars(select(ForecastRun).where(ForecastRun.status.in_([QUEUED, RUNNING])))
    return any(_aware(run.created_at) > cutoff and wanted & set(run.product_ids) for run in active)


def create_run(db: Session, user_id: int, data: RunCreate) -> ForecastRun:
    product_ids = _resolve_products(db, data.product_ids)
    if _overlaps_active_run(db, product_ids):
        raise RunInProgress
    run = ForecastRun(created_by=user_id, horizon=data.horizon, granularity=data.granularity,
                      allowed_models=data.models, product_ids=product_ids, skipped=[])
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def mark_failed(db: Session, run: ForecastRun, reason: str) -> None:
    run.status = FAILED
    run.error = reason
    run.finished_at = datetime.now(UTC)
    db.commit()


def _sales_by_product(db: Session, product_ids: list[int]) -> dict[int, list]:
    query = select(SalesRecord.product_id, SalesRecord.period, SalesRecord.quantity).where(
        SalesRecord.product_id.in_(product_ids))
    sales = defaultdict(list)
    for product_id, period, quantity in db.execute(query):
        sales[product_id].append((period, quantity))
    return sales


def execute_run(db: Session, run_id: int) -> None:
    """Runs in the background worker. Any failure is saved on the run, for the planner to see."""
    run = db.get(ForecastRun, run_id)
    if run is None or run.status != QUEUED:
        return
    run.status = RUNNING
    db.commit()

    try:
        sales = _sales_by_product(db, run.product_ids)
        skipped = []
        for product_id in run.product_ids:
            records = sales.get(product_id)
            if not records:
                skipped.append({"product_id": product_id, "reason": NO_HISTORY})
                continue
            model, points = engine.forecast_product(records, run.horizon, run.granularity,
                                                    run.allowed_models)
            db.add_all(ForecastLine(run_id=run.id, product_id=product_id, model=model,
                                    **vars(point)) for point in points)
    except Exception:  # a worker must always leave the run in a final state
        logger.exception("Forecast run %s failed", run_id)
        db.rollback()
        mark_failed(db, db.get(ForecastRun, run_id), "The forecast could not be completed")
        return

    run.skipped = skipped
    if len(skipped) == len(run.product_ids):
        mark_failed(db, run, "None of the selected products have sales history")
        return
    run.status = DONE
    run.finished_at = datetime.now(UTC)
    db.commit()


def run_details(db: Session, run: ForecastRun, product_id: int | None = None) -> dict:
    query = select(ForecastLine, Product.code).join(Product, ForecastLine.product_id == Product.id)
    query = query.where(ForecastLine.run_id == run.id)
    if product_id is not None:
        query = query.where(ForecastLine.product_id == product_id)
    grouped: dict[int, dict] = {}
    for line, code in db.execute(query.order_by(Product.code, ForecastLine.period)):
        product = grouped.setdefault(line.product_id, {
            "product_id": line.product_id, "code": code, "model": line.model, "points": []})
        product["points"].append(line)
    return {
        "run_id": run.id, "status": run.status, "horizon": run.horizon,
        "granularity": run.granularity, "error": run.error, "skipped": run.skipped,
        "products": list(grouped.values()),
    }


def actual_history(db: Session, product_id: int, granularity: str) -> list[dict]:
    records = _sales_by_product(db, [product_id]).get(product_id, [])
    if not records:
        return []
    series = engine.demand_series(records, granularity)
    return [{"period": period.date(), "actual": float(value)} for period, value in series.items()]
