from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.masterdata.models import Product
from app.sales import parser
from app.sales.models import ImportRun, SalesRecord

MAX_STORED_ERRORS = 1000  # the rejected count stays exact even when the list is cut short


class ConcurrentImport(Exception):
    pass


def _check_row(row: dict, products: dict[str, int], today: date):
    """Returns (values, None) for a good row, or (None, (field, message)) for a bad one."""
    code = str(row.get("product_code") or "").strip().upper()
    if not code:
        return None, ("product_code", "Product code is missing")
    product_id = products.get(code)
    if product_id is None:
        return None, ("product_code", f"Unknown product: {code}")

    try:
        period = parser.parse_date(row.get("date"))
    except ValueError:
        return None, ("date", "Date must be in the format YYYY-MM-DD")
    if period > today:
        return None, ("date", "Date cannot be in the future")

    try:
        quantity = parser.parse_quantity(row.get("quantity"))
    except (ValueError, OverflowError):
        return None, ("quantity", "Quantity must be a whole number")
    if quantity < 0:
        return None, ("quantity", "Quantity cannot be negative")
    if quantity > parser.MAX_QUANTITY:
        return None, ("quantity", "Quantity is too large")

    region = str(row.get("region") or "").strip()
    if len(region) > parser.MAX_REGION_LENGTH:
        return None, ("region", "Region is too long")
    return (product_id, period, region, quantity), None


def import_sales(db: Session, user_id: int, filename: str, content: bytes) -> ImportRun:
    """Stores every valid row in one transaction and records the rest for the error report.

    Sending the same period again updates the existing figure, so re-imports never duplicate.
    """
    rows = parser.read_rows(filename, content)
    products = {code: id_ for id_, code in db.execute(select(Product.id, Product.code))}
    today = date.today()

    valid: dict[tuple, int] = {}
    errors: list[dict] = []
    rejected = 0
    for number, row in rows:
        values, problem = _check_row(row, products, today)
        if problem is None and values[:3] in valid:
            problem = ("date", "Duplicate of an earlier row for this product, date and region")
        if problem is not None:
            rejected += 1
            if len(errors) < MAX_STORED_ERRORS:
                errors.append({"row": number, "field": problem[0], "message": problem[1]})
            continue
        valid[values[:3]] = values[3]

    product_ids = {key[0] for key in valid}
    existing = {}
    if product_ids:
        records = db.scalars(select(SalesRecord).where(SalesRecord.product_id.in_(product_ids)))
        existing = {(r.product_id, r.period, r.region): r for r in records}

    imported = updated = 0
    for key, quantity in valid.items():
        record = existing.get(key)
        if record is None:
            db.add(SalesRecord(product_id=key[0], period=key[1], region=key[2], quantity=quantity))
            imported += 1
        else:
            record.quantity = quantity
            updated += 1

    run = ImportRun(user_id=user_id, filename=(filename or "")[:255], imported=imported,
                    updated=updated, rejected=rejected, errors=errors)
    db.add(run)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConcurrentImport from exc
    db.refresh(run)
    return run


def sales_for_product(db: Session, product_id: int) -> list[SalesRecord]:
    query = select(SalesRecord).where(SalesRecord.product_id == product_id)
    return list(db.scalars(query.order_by(SalesRecord.period, SalesRecord.region)))
