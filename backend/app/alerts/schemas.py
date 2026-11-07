
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    alert_type: str
    entity_type: str
    entity_id: int
    title: str
    message: str
    current_value: float | None
    threshold_value: float | None
    is_open: bool
    created_at: datetime
    resolved_at: datetime | None
    notified_at: datetime | None
