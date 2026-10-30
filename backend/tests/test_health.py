from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app import db
from app.main import app

client = TestClient(app)


def test_health_reports_database_up():
    for path in ("/health", "/api/health"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "database": "up"}


def test_health_reports_database_down(monkeypatch):
    def broken_connect():
        raise OperationalError("SELECT 1", {}, Exception("no database"))

    monkeypatch.setattr(db.engine, "connect", broken_connect)
    assert client.get("/api/health").json()["database"] == "down"
