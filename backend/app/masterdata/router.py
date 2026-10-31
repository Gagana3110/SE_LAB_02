from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.deps import CurrentUser, DbSession, require_roles
from app.auth.models import Role
from app.masterdata import service
from app.masterdata.models import Product, RawMaterial
from app.masterdata.schemas import BomLineOut, BomUpdate, ItemCreate, ItemOut, ItemUpdate

router = APIRouter(prefix="/api")
admin_only = Depends(require_roles(Role.ADMINISTRATOR))
DUPLICATE_CODE = "This code is already in use"


def _get_or_404(db, model, item_id: int):
    item = db.get(model, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
    return item


def _add_item_routes(path: str, model) -> None:
    """Products and raw materials behave the same: any role can read, only Administrators write."""

    def list_items(_: CurrentUser, db: DbSession, active_only: bool = False):
        return service.list_items(db, model, active_only)

    def get_item(item_id: int, _: CurrentUser, db: DbSession):
        return _get_or_404(db, model, item_id)

    def create_item(body: ItemCreate, db: DbSession):
        try:
            return service.create_item(db, model, body)
        except service.DuplicateCode as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, DUPLICATE_CODE) from exc

    def update_item(item_id: int, body: ItemUpdate, db: DbSession):
        try:
            return service.update_item(db, _get_or_404(db, model, item_id), body)
        except service.DuplicateCode as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, DUPLICATE_CODE) from exc

    router.add_api_route(path, list_items, response_model=list[ItemOut])
    router.add_api_route(f"{path}/{{item_id}}", get_item, response_model=ItemOut)
    router.add_api_route(path, create_item, methods=["POST"], response_model=ItemOut,
                         status_code=status.HTTP_201_CREATED, dependencies=[admin_only])
    router.add_api_route(f"{path}/{{item_id}}", update_item, methods=["PATCH"],
                         response_model=ItemOut, dependencies=[admin_only])


_add_item_routes("/products", Product)
_add_item_routes("/materials", RawMaterial)


@router.get("/products/{item_id}/bom", response_model=list[BomLineOut])
def get_bom(item_id: int, _: CurrentUser, db: DbSession):
    return _get_or_404(db, Product, item_id).bom_lines


@router.put("/products/{item_id}/bom", response_model=list[BomLineOut], dependencies=[admin_only])
def replace_bom(item_id: int, body: BomUpdate, db: DbSession):
    product = _get_or_404(db, Product, item_id)
    try:
        return service.replace_bom(db, product, body.lines)
    except service.InvalidBomMaterial as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"These materials do not exist or are inactive: {exc.args[0]}",
        ) from exc
