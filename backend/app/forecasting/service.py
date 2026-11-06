
import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.forecasting import engine
from app.forecasting.models import (
    DONE,
    FAILED,
    QUEUED,
    RUNNING,
    AuditLog,
    ForecastApproval,
    ForecastLine,
    ForecastMetric,
    ForecastOverride,
    ForecastRun,
)
from app.forecasting.schemas import ForecastOverrideCreate, RunCreate
from app.inventory.models import MarketIndicator
from app.masterdata.models import Product
from app.sales.models import SalesRecord

logger = logging.getLogger(__name__)

STALE_AFTER = timedelta(minutes=30)
NO_HISTORY = "No sales history"


class UnknownProducts(Exception):
    pass


class RunInProgress(Exception):
    pass


def _resolve_products(db: Session, requested: list[int] | str) -> list[int]:
    active = set(
        db.scalars(
            select(Product.id).where(Product.active.is_(True))
        )
    )

    if requested == "ALL":
        if not active:
            raise UnknownProducts([])
        return sorted(active)

    wanted = set(requested)

    if wanted - active:
        raise UnknownProducts(sorted(wanted - active))

    return sorted(wanted)


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _overlaps_active_run(db: Session, product_ids: list[int]) -> bool:
    cutoff = datetime.now(UTC) - STALE_AFTER
    wanted = set(product_ids)

    active = db.scalars(
        select(ForecastRun).where(
            ForecastRun.status.in_([QUEUED, RUNNING])
        )
    )

    return any(
        _aware(run.created_at) > cutoff
        and wanted & set(run.product_ids)
        for run in active
    )


def create_run(db: Session, user_id: int, data: RunCreate) -> ForecastRun:
    product_ids = _resolve_products(db, data.product_ids)

    if _overlaps_active_run(db, product_ids):
        raise RunInProgress

    run = ForecastRun(
        created_by=user_id,
        horizon=data.horizon,
        granularity=data.granularity,
        allowed_models=data.models,
        product_ids=product_ids,
        skipped=[],
    )

    db.add(run)
    db.commit()
    db.refresh(run)

    return run


def mark_failed(db: Session, run: ForecastRun, reason: str) -> None:
    run.status = FAILED
    run.error = reason
    run.finished_at = datetime.now(UTC)
    db.commit()


def _sales_by_product(
    db: Session,
    product_ids: list[int],
) -> dict[int, list]:
    query = select(
        SalesRecord.product_id,
        SalesRecord.period,
        SalesRecord.quantity,
    ).where(
        SalesRecord.product_id.in_(product_ids)
    )

    sales = defaultdict(list)

    for product_id, period, quantity in db.execute(query):
        sales[product_id].append((period, quantity))

    return sales


def _indicators_by_product(
    db: Session,
    product_ids: list[int],
) -> dict[int, pd.DataFrame]:
    """Load historical market indicators for the selected products."""

    query = select(MarketIndicator).where(
        MarketIndicator.product_id.in_(product_ids)
    ).order_by(
        MarketIndicator.product_id,
        MarketIndicator.period,
    )

    grouped = defaultdict(list)

    for item in db.scalars(query):
        grouped[item.product_id].append(
            {
                "period": item.period,
                "promotion": int(bool(item.promotion)),
                "price_change_pct": float(item.price_change_pct or 0),
                "holiday_flag": int(bool(item.holiday_flag)),
                "trend_index": float(item.trend_index or 0),
            }
        )

    result = {}

    for product_id, rows in grouped.items():
        frame = pd.DataFrame(rows)
        frame["period"] = pd.to_datetime(frame["period"])
        frame = frame.set_index("period").sort_index()
        result[product_id] = frame

    return result


def execute_run(db: Session, run_id: int) -> None:
    """Execute a forecast run and persist forecasts and evaluation metrics."""

    run = db.get(ForecastRun, run_id)

    if run is None or run.status != QUEUED:
        return

    run.status = RUNNING
    db.commit()

    try:
        sales = _sales_by_product(db, run.product_ids)
        indicators = _indicators_by_product(db, run.product_ids)

        skipped = []

        for product_id in run.product_ids:
            records = sales.get(product_id)

            if not records:
                skipped.append(
                    {
                        "product_id": product_id,
                        "reason": NO_HISTORY,
                    }
                )
                continue

            indicator_frame = indicators.get(product_id)

            model, points, metrics = engine.forecast_product_with_metrics(
                records=records,
                horizon=run.horizon,
                granularity=run.granularity,
                allowed=run.allowed_models,
                indicators=indicator_frame,
            )

            db.add_all(
                ForecastLine(
                    run_id=run.id,
                    product_id=product_id,
                    model=model,
                    **vars(point),
                )
                for point in points
            )

            db.add(
                ForecastMetric(
                    run_id=run.id,
                    product_id=product_id,
                    model=metrics.model,
                    mape=metrics.mape,
                    mae=metrics.mae,
                    bias=metrics.bias,
                    confidence=metrics.confidence,
                )
            )

        db.flush()

    except Exception:
        logger.exception("Forecast run %s failed", run_id)
        db.rollback()

        failed_run = db.get(ForecastRun, run_id)

        if failed_run is not None:
            mark_failed(
                db,
                failed_run,
                "The forecast could not be completed",
            )

        return

    run.skipped = skipped

    if len(skipped) == len(run.product_ids):
        mark_failed(
            db,
            run,
            "None of the selected products have sales history",
        )
        return

    run.status = DONE
    run.finished_at = datetime.now(UTC)
    db.commit()


def recent_runs(db: Session, limit: int = 20) -> list[ForecastRun]:
    return list(
        db.scalars(
            select(ForecastRun)
            .order_by(ForecastRun.id.desc())
            .limit(limit)
        )
    )


def run_details(
    db: Session,
    run: ForecastRun,
    product_id: int | None = None,
) -> dict:
    query = (
        select(ForecastLine, Product.code)
        .join(Product, ForecastLine.product_id == Product.id)
        .where(ForecastLine.run_id == run.id)
    )

    if product_id is not None:
        query = query.where(
            ForecastLine.product_id == product_id
        )

    grouped = {}

    for line, code in db.execute(
        query.order_by(Product.code, ForecastLine.period)
    ):
        product = grouped.setdefault(
            line.product_id,
            {
                "product_id": line.product_id,
                "code": code,
                "model": line.model,
                "points": [],
            },
        )

        product["points"].append(line)

    metric_query = select(ForecastMetric).where(
        ForecastMetric.run_id == run.id
    )

    if product_id is not None:
        metric_query = metric_query.where(
            ForecastMetric.product_id == product_id
        )

    for metric in db.scalars(metric_query):
        if metric.product_id in grouped:
            grouped[metric.product_id]["metrics"] = {
                "mape": metric.mape,
                "mae": metric.mae,
                "bias": metric.bias,
                "confidence": metric.confidence,
            }

    return {
        "run_id": run.id,
        "status": run.status,
        "horizon": run.horizon,
        "granularity": run.granularity,
        "error": run.error,
        "skipped": run.skipped,
        "products": list(grouped.values()),
    }


def actual_history(
    db: Session,
    product_id: int,
    granularity: str,
) -> list[dict]:
    records = _sales_by_product(db, [product_id]).get(
        product_id, []
    )

    if not records:
        return []

    series = engine.demand_series(records, granularity)

    return [
        {
            "period": period.date(),
            "actual": float(value),
        }
        for period, value in series.items()
    ]


# ---------------------------------------------------------
# DFS-16: overrides, approval and audit history
# ---------------------------------------------------------

class ForecastNotEditable(Exception):
    pass


class ForecastPointNotFound(Exception):
    pass


class ForecastAlreadyApproved(Exception):
    pass


def create_override(
    db: Session,
    run_id: int,
    user_id: int,
    data: ForecastOverrideCreate,
) -> ForecastOverride:

    run = db.scalar(
        select(ForecastRun)
        .where(ForecastRun.id == run_id)
        .with_for_update()
    )

    if run is None:
        raise ForecastPointNotFound("Forecast run not found")

    if run.status != DONE:
        raise ForecastNotEditable(
            "Only completed forecast runs can be overridden"
        )

    if db.scalar(
        select(ForecastApproval.id).where(
            ForecastApproval.run_id == run_id
        )
    ):
        raise ForecastAlreadyApproved(
            "An approved forecast cannot be overridden"
        )

    line = db.scalar(
        select(ForecastLine)
        .where(
            ForecastLine.run_id == run_id,
            ForecastLine.product_id == data.product_id,
            ForecastLine.period == data.period,
        )
        .with_for_update()
    )

    if line is None:
        raise ForecastPointNotFound(
            "Forecast point not found for this run, product and period"
        )

    old_value = float(line.forecast)
    new_value = float(data.new_forecast)

    line.forecast = new_value

    record = ForecastOverride(
        run_id=run_id,
        product_id=data.product_id,
        period=data.period,
        old_value=old_value,
        new_value=new_value,
        reason=data.reason,
        user_id=user_id,
    )

    db.add(record)

    db.add(
        AuditLog(
            user_id=user_id,
            action="FORECAST_OVERRIDE",
            run_id=run_id,
            product_id=data.product_id,
            period=data.period,
            old_value=old_value,
            new_value=new_value,
            reason=data.reason,
        )
    )

    db.commit()
    db.refresh(record)

    return record


def approve_forecast(
    db: Session,
    run_id: int,
    user_id: int,
) -> ForecastApproval:

    run = db.scalar(
        select(ForecastRun)
        .where(ForecastRun.id == run_id)
        .with_for_update()
    )

    if run is None:
        raise ForecastPointNotFound("Forecast run not found")

    if run.status != DONE:
        raise ForecastNotEditable(
            "Only completed forecast runs can be approved"
        )

    if db.scalar(
        select(ForecastApproval.id).where(
            ForecastApproval.run_id == run_id
        )
    ):
        raise ForecastAlreadyApproved(
            "This forecast run has already been approved"
        )

    approval = ForecastApproval(
        run_id=run_id,
        approved_by=user_id,
    )

    db.add(approval)

    db.add(
        AuditLog(
            user_id=user_id,
            action="FORECAST_APPROVED",
            run_id=run_id,
            old_value=None,
            new_value=None,
        )
    )

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ForecastAlreadyApproved(
            "This forecast run has already been approved"
        ) from exc

    db.refresh(approval)

    return approval


def list_audit_logs(
    db: Session,
    limit: int = 100,
) -> list[AuditLog]:

    statement = (
        select(AuditLog)
        .order_by(
            AuditLog.timestamp.desc(),
            AuditLog.id.desc(),
        )
        .limit(limit)
    )

    return list(db.scalars(statement))
