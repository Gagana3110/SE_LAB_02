"""Background jobs, so that long forecast runs never block web requests (SAD ADR-3)."""

from celery import Celery

from app.auth import models as auth_models  # noqa: F401 - registers the tables for the worker
from app.config import settings
from app.db import SessionLocal
from app.forecasting import service

JOB_TIME_LIMIT_SECONDS = 20 * 60

celery_app = Celery("dfs", broker=settings.redis_url)
celery_app.conf.update(
    task_ignore_result=True,
    task_publish_retry=False,
    broker_connection_retry_on_startup=True,
    broker_connection_timeout=3,
    broker_transport_options={"socket_connect_timeout": 3},
)


@celery_app.task(name="forecast.run", time_limit=JOB_TIME_LIMIT_SECONDS)
def run_forecast(run_id: int) -> None:
    with SessionLocal() as db:
        service.execute_run(db, run_id)
