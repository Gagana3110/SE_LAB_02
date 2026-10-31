from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict

from app.auth.deps import CurrentUser, DbSession, require_roles
from app.auth.models import Role, User
from app.masterdata.models import Product
from app.safe_csv import to_csv
from app.sales import parser, service
from app.sales.models import ImportRun

router = APIRouter(prefix="/api")
planner_only = require_roles(Role.DEMAND_PLANNER)


class RowError(BaseModel):
    row: int
    field: str
    message: str


class ImportResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    imported: int
    updated: int
    rejected: int
    errors: list[RowError]


class SalesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    period: date
    quantity: int
    region: str


@router.post("/imports/sales", response_model=ImportResult)
async def import_sales(file: UploadFile, db: DbSession, user: User = Depends(planner_only)):
    content = await file.read(parser.MAX_UPLOAD_BYTES + 1)
    if len(content) > parser.MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "The limit is 10 MB")
    try:
        return service.import_sales(db, user.id, file.filename, content)
    except parser.UnsupportedFile as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc
    except parser.BadLayout as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except service.ConcurrentImport as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Another import changed the same data; please try again"
        ) from exc


@router.get("/imports/{run_id}/errors.csv", dependencies=[Depends(planner_only)])
def error_report(run_id: int, db: DbSession) -> Response:
    run = db.get(ImportRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import not found")
    rows = [[e["row"], e["field"], e["message"]] for e in run.errors]
    return Response(
        to_csv(["row", "field", "message"], rows),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="import-{run_id}-errors.csv"'},
    )


@router.get("/products/{product_id}/sales", response_model=list[SalesOut])
def product_sales(product_id: int, _: CurrentUser, db: DbSession):
    if db.get(Product, product_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
    return service.sales_for_product(db, product_id)
