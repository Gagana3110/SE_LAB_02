
from fastapi import APIRouter, Depends

from sqlalchemy import select

from app.alerts import service
from app.alerts.models import Alert
from app.alerts.schemas import AlertOut
from app.auth.deps import DbSession, require_roles
from app.auth.models import Role, User

router = APIRouter(prefix="/api/alerts", tags=["Alerts"])

alert_readers = require_roles(
    Role.ADMINISTRATOR,
    Role.INVENTORY_MANAGER,
    Role.DEMAND_PLANNER,
    Role.PROCUREMENT_MANAGER,
)


@router.get("", response_model=list[AlertOut])
def get_alerts(
    db: DbSession,
    _: User = Depends(alert_readers),
    open_only: bool = True,
):
    query = select(Alert)

    if open_only:
        query = query.where(Alert.is_open.is_(True))

    return list(
        db.scalars(
            query.order_by(Alert.created_at.desc(), Alert.id.desc())
        )
    )


@router.post("/evaluate")
def evaluate_alerts(
    db: DbSession,
    _: User = Depends(
        require_roles(Role.ADMINISTRATOR, Role.INVENTORY_MANAGER)
    ),
):
    count = service.evaluate_all_alerts(db)
    return {"created_alerts": count}
