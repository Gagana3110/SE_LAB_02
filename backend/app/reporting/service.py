from sqlalchemy import func

from app.forecasting.models import ForecastRun
from app.inventory.models import StockMovement
from app.procurement.models import PurchaseOrder
from app.suppliers.models import Supplier


def dashboard_kpis(db):
    total_forecast_runs = (
        db.query(func.count(ForecastRun.id))
        .scalar()
        or 0
    )

    upcoming_purchase_orders = (
        db.query(func.count(PurchaseOrder.id))
        .filter(PurchaseOrder.status == "DRAFT")
        .scalar()
        or 0
    )

    active_suppliers = (
        db.query(func.count(Supplier.id))
        .filter(Supplier.active.is_(True))
        .scalar()
        or 0
    )

    stock_movements = (
        db.query(func.count(StockMovement.id))
        .scalar()
        or 0
    )

    return {
        "totalForecastRuns": total_forecast_runs,
        "upcomingPurchaseOrders": upcoming_purchase_orders,
        "activeSuppliers": active_suppliers,
        "totalStockMovements": stock_movements,
    }
