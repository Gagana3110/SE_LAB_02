from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.auth.deps import CurrentUser, DbSession
from app.auth.models import Role
from app.forecasting.models import ForecastLine
from app.procurement.models import RecommendationLine
from app.reporting import service
from app.reporting.exports import export_csv, export_pdf

router = APIRouter(prefix="/api/reports", tags=["Reporting"])


@router.get("/dashboard")
def dashboard(user: CurrentUser, db: DbSession):
    return service.dashboard_kpis(db)


@router.get("/export/{report_type}")
def export_report(
    report_type: str,
    db: DbSession,
    user: CurrentUser,
    file_format: str = Query(default="csv", alias="format"),
):
    if file_format not in {"csv", "pdf"}:
        raise HTTPException(400, "Format must be csv or pdf")

    if report_type == "forecasts":
        if user.role not in {Role.ADMINISTRATOR, Role.DEMAND_PLANNER}:
            raise HTTPException(403, "Not authorized")
        records = db.query(ForecastLine).all()
        headers = ["Run ID", "Product ID", "Period", "Model", "Forecast"]
        rows = [
            [r.run_id, r.product_id, r.period, r.model, r.forecast]
            for r in records
        ]

    elif report_type == "material-requirements":
        if user.role not in {
            Role.ADMINISTRATOR,
            Role.INVENTORY_MANAGER,
            Role.PROCUREMENT_MANAGER,
        }:
            raise HTTPException(403, "Not authorized")
        records = db.query(RecommendationLine).all()
        headers = ["Material ID", "Need Date", "Net Requirement", "Order Quantity"]
        rows = [
            [r.material_id, r.need_date, r.net_requirement, r.total_order_qty]
            for r in records
        ]

    elif report_type == "purchase-recommendations":
        if user.role not in {Role.ADMINISTRATOR, Role.PROCUREMENT_MANAGER}:
            raise HTTPException(403, "Not authorized")
        records = db.query(RecommendationLine).all()
        headers = ["Material ID", "Need Date", "Net Requirement", "Order Quantity", "Status"]
        rows = [
            [r.material_id, r.need_date, r.net_requirement, r.total_order_qty, r.status]
            for r in records
        ]

    else:
        raise HTTPException(404, "Unknown report type")

    if file_format == "csv":
        content = export_csv(headers, rows)
        media_type = "text/csv"
    else:
        content = export_pdf(report_type.replace("-", " ").title(), headers, rows)
        media_type = "application/pdf"

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{report_type}.{file_format}"'
            )
        },
    )
