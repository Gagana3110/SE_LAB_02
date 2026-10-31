from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.auth import models as auth_models  # noqa: F401 - registers the tables
from app.auth.router import router as auth_router
from app.auth.service import bootstrap_admin
from app.db import Base, SessionLocal, database_is_up, engine
from app.errors import register_error_handling
from app.masterdata.router import router as masterdata_router
from app.sales.router import router as sales_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        bootstrap_admin(session)
    yield


app = FastAPI(title="Demand Forecasting System", version="0.1.0", lifespan=lifespan)
register_error_handling(app)
app.include_router(auth_router)
app.include_router(masterdata_router)
app.include_router(sales_router)


@app.get("/health")
@app.get("/api/health")
def health() -> dict[str, str]:
    """Used by the uptime monitor (DFS-NF-004) and the web UI."""
    return {"status": "ok", "database": "up" if database_is_up() else "down"}
