from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.masterdata.models import RawMaterial
from app.suppliers.models import MaterialSupplier, Supplier
from app.suppliers.schemas import LinkIn, SupplierCreate, SupplierUpdate


class DuplicateCode(Exception):
    pass


class InvalidSupplier(Exception):
    pass


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateCode from exc


def list_suppliers(db: Session, active_only: bool = False) -> list[Supplier]:
    query = select(Supplier).order_by(Supplier.code)
    if active_only:
        query = query.where(Supplier.active.is_(True))
    return list(db.scalars(query))


def create_supplier(db: Session, data: SupplierCreate) -> Supplier:
    supplier = Supplier(**data.model_dump())
    db.add(supplier)
    _commit(db)
    db.refresh(supplier)
    return supplier


def update_supplier(db: Session, supplier: Supplier, data: SupplierUpdate) -> Supplier:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(supplier, field, value)
    _commit(db)
    db.refresh(supplier)
    return supplier


def links_for_material(db: Session, material_id: int) -> list[MaterialSupplier]:
    query = select(MaterialSupplier).where(MaterialSupplier.material_id == material_id)
    return list(db.scalars(query.order_by(MaterialSupplier.preferred.desc(), MaterialSupplier.id)))


def replace_links(db: Session, material_id: int, links: list[LinkIn]) -> list[MaterialSupplier]:
    """Replaces all of a material's suppliers at once, so a bad request changes nothing."""
    wanted = {link.supplier_id for link in links}
    found = db.scalars(select(Supplier).where(Supplier.id.in_(wanted))).all()
    usable = {supplier.id for supplier in found if supplier.active}
    if wanted - usable:
        raise InvalidSupplier(sorted(wanted - usable))

    db.execute(delete(MaterialSupplier).where(MaterialSupplier.material_id == material_id))
    db.add_all(MaterialSupplier(material_id=material_id, supplier_id=link.supplier_id,
                                preferred=link.preferred) for link in links)
    db.commit()
    return links_for_material(db, material_id)


def materials_without_active_supplier(db: Session) -> list[RawMaterial]:
    """Active materials that purchase planning must flag (AC-006)."""
    covered = (
        select(MaterialSupplier.material_id)
        .join(Supplier, MaterialSupplier.supplier_id == Supplier.id)
        .where(Supplier.active.is_(True))
    )
    query = select(RawMaterial).where(RawMaterial.active.is_(True), RawMaterial.id.not_in(covered))
    return list(db.scalars(query.order_by(RawMaterial.code)))
