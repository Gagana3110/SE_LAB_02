from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.masterdata.models import BomLine, Product, RawMaterial
from app.masterdata.schemas import BomLineIn, ItemCreate, ItemUpdate

Item = Product | RawMaterial


class DuplicateCode(Exception):
    pass


class InvalidBomMaterial(Exception):
    pass


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateCode from exc


def list_items(db: Session, model: type[Item], active_only: bool = False) -> list[Item]:
    query = select(model).order_by(model.code)
    if active_only:
        query = query.where(model.active.is_(True))
    return list(db.scalars(query))


def create_item(db: Session, model: type[Item], data: ItemCreate) -> Item:
    item = model(**data.model_dump())
    db.add(item)
    _commit(db)
    db.refresh(item)
    return item


def update_item(db: Session, item: Item, data: ItemUpdate) -> Item:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    _commit(db)
    db.refresh(item)
    return item


def replace_bom(db: Session, product: Product, lines: list[BomLineIn]) -> list[BomLine]:
    """Replaces the whole BOM in one transaction, so a bad line leaves the old BOM untouched."""
    wanted = {line.material_id for line in lines}
    materials = db.scalars(select(RawMaterial).where(RawMaterial.id.in_(wanted))).all()
    usable = {material.id for material in materials if material.active}
    if wanted - usable:
        raise InvalidBomMaterial(sorted(wanted - usable))

    product.bom_lines.clear()
    db.flush()  # removes old rows first, so re-adding a material cannot break the unique rule
    product.bom_lines.extend(
        BomLine(material_id=line.material_id, qty_per_unit=line.qty_per_unit) for line in lines
    )
    db.commit()
    db.refresh(product)
    return product.bom_lines
