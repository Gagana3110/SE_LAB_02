from fastapi import FastAPI

from app.db import database_is_up

app = FastAPI(title="Demand Forecasting System", version="0.1.0")


@app.get("/health")
@app.get("/api/health")
def health() -> dict[str, str]:
    """Used by the uptime monitor (DFS-NF-004) and the web UI."""
    return {"status": "ok", "database": "up" if database_is_up() else "down"}
