from fastapi import APIRouter, Depends, HTTPException, Query, status
from kombu.exceptions import OperationalError as QueueUnavailable

from app.auth.deps import CurrentUser, DbSession, require_roles
from app.auth.models import Role, User
from app.forecasting import service
from app.forecasting.models import ForecastRun
from app.forecasting.schemas import (
    AuditLogOut,
    ForecastApprovalOut,
    ForecastOverrideCreate,
    ForecastOverrideOut,
    ProductChart,
    RunAccepted,
    RunCreate,
    RunOut,
    RunSummary,
)
from app.forecasting.tasks import run_forecast

router = APIRouter(prefix="/api/forecasts")
audit_router = APIRouter()
planner_only = require_roles(Role.DEMAND_PLANNER)


def _get_run(db, run_id: int) -> ForecastRun:
    run = db.get(ForecastRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Forecast run not found")
    return run


@router.post("/runs", response_model=RunAccepted, status_code=status.HTTP_202_ACCEPTED)
def start_run(body: RunCreate, db: DbSession, user: User = Depends(planner_only)):
    try:
        run = service.create_run(db, user.id, body)
    except service.UnknownProducts as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"These products do not exist or are inactive: {exc.args[0]}",
        ) from exc
    except service.RunInProgress as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A forecast for these products is already running"
        ) from exc

    run_id, run_status = run.id, run.status
    try:
        run_forecast.delay(run_id)
    except QueueUnavailable as exc:
        service.mark_failed(db, run, "The forecast service is unavailable")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "The forecast service is unavailable"
        ) from exc
    return {"run_id": run_id, "status": run_status}


@router.get("/runs", response_model=list[RunSummary])
def list_runs(_: CurrentUser, db: DbSession):
    return service.recent_runs(db)


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: int, _: CurrentUser, db: DbSession):
    return service.run_details(db, _get_run(db, run_id))


@router.get("/runs/{run_id}/products/{product_id}", response_model=ProductChart)
def product_chart(run_id: int, product_id: int, _: CurrentUser, db: DbSession):
    run = _get_run(db, run_id)
    products = service.run_details(db, run, product_id)["products"]
    if not products:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No forecast for this product in this run"
        )
    return {**products[0], "history": service.actual_history(db, product_id, run.granularity)}


@router.post("/runs/{run_id}/override", response_model=ForecastOverrideOut)
def override_forecast(
    run_id: int,
    body: ForecastOverrideCreate,
    db: DbSession,
    user: User = Depends(planner_only),
):
    try:
        return service.create_override(db, run_id, user.id, body)
    except service.ForecastPointNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except service.ForecastNotEditable as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except service.ForecastAlreadyApproved as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/runs/{run_id}/approve", response_model=ForecastApprovalOut)
def approve_forecast(run_id: int, db: DbSession, user: User = Depends(planner_only)):
    try:
        return service.approve_forecast(db, run_id, user.id)
    except service.ForecastPointNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except service.ForecastNotEditable as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except service.ForecastAlreadyApproved as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@audit_router.get("/api/audit-log", response_model=list[AuditLogOut])
def get_audit_log(
    db: DbSession,
    _: User = Depends(planner_only),
    limit: int = Query(default=100, ge=1, le=500),
):
    return service.list_audit_logs(db, limit)
