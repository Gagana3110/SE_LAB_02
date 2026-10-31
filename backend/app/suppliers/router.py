from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.deps import DbSession, require_roles
from app.auth.models import Role
from app.masterdata.models import RawMaterial
from app.suppliers import service
from app.suppliers.models import Supplier
from app.suppliers.schemas import (
    LinkOut,
    LinksUpdate,
    MaterialGap,
    SupplierCreate,
    SupplierOut,
    SupplierUpdate,
)

router = APIRouter(prefix="/api")
admin_only = Depends(require_roles(Role.ADMINISTRATOR))
# Supplier prices are commercially sensitive (SO-1), so only the roles that buy can read them.
buyers = Depends(require_roles(Role.ADMINISTRATOR, Role.PROCUREMENT_MANAGER))
DUPLICATE_CODE = "This code is already in use"


def _get_supplier(db, supplier_id: int) -> Supplier:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Supplier not found")
    return supplier


def _check_material(db, material_id: int) -> None:
    if db.get(RawMaterial, material_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")


@router.get("/suppliers", response_model=list[SupplierOut], dependencies=[buyers])
def list_suppliers(db: DbSession, active_only: bool = False):
    return service.list_suppliers(db, active_only)


@router.get("/suppliers/{supplier_id}", response_model=SupplierOut, dependencies=[buyers])
def get_supplier(supplier_id: int, db: DbSession):
    return _get_supplier(db, supplier_id)


@router.post("/suppliers", response_model=SupplierOut, status_code=status.HTTP_201_CREATED,
             dependencies=[admin_only])
def create_supplier(body: SupplierCreate, db: DbSession):
    try:
        return service.create_supplier(db, body)
    except service.DuplicateCode as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, DUPLICATE_CODE) from exc


@router.patch("/suppliers/{supplier_id}", response_model=SupplierOut, dependencies=[admin_only])
def update_supplier(supplier_id: int, body: SupplierUpdate, db: DbSession):
    try:
        return service.update_supplier(db, _get_supplier(db, supplier_id), body)
    except service.DuplicateCode as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, DUPLICATE_CODE) from exc


@router.get("/materials/{material_id}/suppliers", response_model=list[LinkOut],
            dependencies=[buyers])
def get_links(material_id: int, db: DbSession):
    _check_material(db, material_id)
    return service.links_for_material(db, material_id)


@router.put("/materials/{material_id}/suppliers", response_model=list[LinkOut],
            dependencies=[admin_only])
def replace_links(material_id: int, body: LinksUpdate, db: DbSession):
    _check_material(db, material_id)
    try:
        return service.replace_links(db, material_id, body.links)
    except service.InvalidSupplier as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"These suppliers do not exist or are inactive: {exc.args[0]}",
        ) from exc


@router.get("/purchasing/materials-without-supplier", response_model=list[MaterialGap],
            dependencies=[buyers])
def materials_without_supplier(db: DbSession):
    return service.materials_without_active_supplier(db)
