from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.inventory.models import MarketIndicator, StockMovement
from app.inventory.schemas import MarketIndicatorCreate, StockMovementCreate
from app.masterdata.models import Product, RawMaterial


class UnknownItem(Exception):
    pass


class InsufficientStock(Exception):
    pass


class DuplicateIndicator(Exception):
    pass


def _item_model(item_type: str):
    return Product if item_type == "product" else RawMaterial


def _get_active_item(db: Session, item_type: str, item_id: int):
    model = _item_model(item_type)
    item = db.get(model, item_id)
    if item is None or not item.active:
        raise UnknownItem
    return item


def item_balance(db: Session, item_type: str, item_id: int) -> Decimal:
    """Calculate current stock from the movement ledger; adjustments are signed."""
    movements = db.scalars(
        select(StockMovement).where(
            StockMovement.item_type == item_type,
            StockMovement.item_id == item_id,
        )
    )
    balance = Decimal("0")
    for movement in movements:
        if movement.movement_type == "receipt":
            balance += movement.qty
        elif movement.movement_type == "issue":
            balance -= movement.qty
        else:
            balance += movement.qty
    return balance


def create_movement(db: Session, data: StockMovementCreate) -> StockMovement:
    _get_active_item(db, data.item_type, data.item_id)
    balance = item_balance(db, data.item_type, data.item_id)
    if data.movement_type == "issue" and data.qty > balance:
        raise InsufficientStock
    if data.movement_type == "adjustment" and balance + data.qty < 0:
        raise InsufficientStock

    movement = StockMovement(**data.model_dump())
    db.add(movement)
    db.commit()
    db.refresh(movement)
    return movement


def list_movements(
    db: Session, item_type: str | None = None, item_id: int | None = None
) -> list[StockMovement]:
    query = select(StockMovement)
    if item_type is not None:
        query = query.where(StockMovement.item_type == item_type)
    if item_id is not None:
        query = query.where(StockMovement.item_id == item_id)
    return list(db.scalars(query.order_by(StockMovement.movement_date, StockMovement.id)))


def list_balances(
    db: Session, item_type: str | None = None, item_id: int | None = None
) -> list[dict]:
    items: list[tuple[str, object]] = []
    if item_type in (None, "product"):
        query = select(Product).where(Product.active.is_(True)).order_by(Product.code)
        if item_id is not None:
            query = query.where(Product.id == item_id)
        items.extend(("product", item) for item in db.scalars(query))
    if item_type in (None, "raw_material"):
        query = select(RawMaterial).where(RawMaterial.active.is_(True)).order_by(RawMaterial.code)
        if item_id is not None:
            query = query.where(RawMaterial.id == item_id)
        items.extend(("raw_material", item) for item in db.scalars(query))
    return [
        {
            "item_type": kind,
            "item_id": item.id,
            "code": item.code,
            "name": item.name,
            "unit": item.unit,
            "on_hand_qty": item_balance(db, kind, item.id),
        }
        for kind, item in items
    ]


def create_market_indicator(db: Session, data: MarketIndicatorCreate) -> MarketIndicator:
    product = db.get(Product, data.product_id)
    if product is None or not product.active:
        raise UnknownItem
    indicator = MarketIndicator(**data.model_dump())
    db.add(indicator)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateIndicator from exc
    db.refresh(indicator)
    return indicator


def list_market_indicators(
    db: Session, product_id: int | None = None, period: date | None = None
) -> list[MarketIndicator]:
    query = select(MarketIndicator)
    if product_id is not None:
        query = query.where(MarketIndicator.product_id == product_id)
    if period is not None:
        query = query.where(MarketIndicator.period == period)
    return list(db.scalars(query.order_by(MarketIndicator.product_id, MarketIndicator.period)))
