
import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.alerts.service import evaluate_all_alerts
from app.auth.deps import CurrentUser, DbSession, require_roles
from app.auth.models import Role
from app.inventory import service
from app.inventory.schemas import (
    ItemType,
    MarketIndicatorCreate,
    MarketIndicatorOut,
    StockBalanceOut,
    StockMovementCreate,
    StockMovementOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")
stock_writers = Depends(require_roles(Role.ADMINISTRATOR, Role.INVENTORY_MANAGER))
indicator_writers = Depends(require_roles(Role.ADMINISTRATOR, Role.DEMAND_PLANNER))


@router.post(
    "/inventory/movements",
    response_model=StockMovementOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[stock_writers],
)
def post_movement(body: StockMovementCreate, db: DbSession):
    try:
        movement = service.create_movement(db, body)
    except service.UnknownItem as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Active item not found") from exc
    except service.InsufficientStock as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Movement would make on-hand stock negative"
        ) from exc

    try:
        evaluate_all_alerts(db)
    except Exception:
        logger.exception("Alert evaluation failed after stock movement %s", movement.id)

    return movement


@router.get("/inventory/movements", response_model=list[StockMovementOut])
def get_movements(
    _: CurrentUser,
    db: DbSession,
    item_type: ItemType | None = None,
    item_id: int | None = Query(default=None, gt=0),
):
    if item_id is not None and item_type is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "item_type is required with item_id")
    return service.list_movements(db, item_type, item_id)


@router.get("/inventory/balances", response_model=list[StockBalanceOut])
def get_balances(
    _: CurrentUser,
    db: DbSession,
    item_type: ItemType | None = None,
    item_id: int | None = Query(default=None, gt=0),
):
    if item_id is not None and item_type is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "item_type is required with item_id")
    return service.list_balances(db, item_type, item_id)


@router.post(
    "/market-indicators",
    response_model=MarketIndicatorOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[indicator_writers],
)
def post_market_indicator(body: MarketIndicatorCreate, db: DbSession):
    try:
        return service.create_market_indicator(db, body)
    except service.UnknownItem as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Active product not found") from exc
    except service.DuplicateIndicator as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "An indicator already exists for this product and period"
        ) from exc


@router.get("/market-indicators", response_model=list[MarketIndicatorOut])
def get_market_indicators(
    _: CurrentUser,
    db: DbSession,
    product_id: int | None = Query(default=None, gt=0),
    period: date | None = None,
):
    return service.list_market_indicators(db, product_id, period)
