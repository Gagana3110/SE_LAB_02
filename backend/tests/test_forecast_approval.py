from datetime import date

import pytest

from app.auth.models import Role
from app.forecasting.models import DONE, AuditLog, ForecastApproval, ForecastLine, ForecastRun
from app.masterdata.models import Product


@pytest.fixture
def planner(login_as):
    return login_as(Role.DEMAND_PLANNER)


def completed_run(db, planner):
    product = Product(code="OVR-001", name="Override test product", unit="piece", active=True)
    db.add(product)
    db.flush()
    run = ForecastRun(
        status=DONE,
        created_by=planner.id,
        horizon=1,
        granularity="MONTH",
        allowed_models=["MA"],
        product_ids=[product.id],
        skipped=[],
    )
    db.add(run)
    db.flush()
    line = ForecastLine(
        run_id=run.id,
        product_id=product.id,
        period=date(2026, 1, 1),
        model="MA",
        forecast=100.0,
        lower80=90.0,
        upper80=110.0,
        lower95=80.0,
        upper95=120.0,
    )
    db.add(line)
    db.commit()
    return run, product, line


def override_payload(product_id, **changes):
    payload = {
        "productId": product_id,
        "period": "2026-01-01",
        "newForecast": 125.0,
        "reason": "Updated after reviewing the latest customer order",
    }
    payload.update(changes)
    return payload


def test_override_rejects_missing_or_blank_reason(client, planner, db):
    run, product, _ = completed_run(db, planner)
    response = client.post(
        f"/api/forecasts/runs/{run.id}/override",
        json=override_payload(product.id, reason="   "),
    )
    assert response.status_code == 400


def test_approval_locks_forecast_against_later_override(client, planner, db):
    run, product, line = completed_run(db, planner)
    approved = client.post(f"/api/forecasts/runs/{run.id}/approve")
    assert approved.status_code == 200
    response = client.post(
        f"/api/forecasts/runs/{run.id}/override",
        json=override_payload(product.id),
    )
    assert response.status_code == 409
    db.refresh(line)
    assert line.forecast == 100.0


def test_override_updates_forecast_and_creates_audit_entry(client, planner, db):
    run, product, line = completed_run(db, planner)
    response = client.post(
        f"/api/forecasts/runs/{run.id}/override",
        json=override_payload(product.id),
    )
    assert response.status_code == 200
    assert response.json()["oldValue"] == 100.0
    assert response.json()["newValue"] == 125.0
    db.refresh(line)
    assert line.forecast == 125.0

    audit = client.get("/api/audit-log")
    assert audit.status_code == 200
    assert len(audit.json()) == 1
    assert audit.json()[0]["action"] == "FORECAST_OVERRIDE"
    assert audit.json()[0]["oldValue"] == 100.0
    assert audit.json()[0]["newValue"] == 125.0


def test_non_planner_cannot_override_approve_or_read_audit(client, login_as, db):
    user = login_as(Role.INVENTORY_MANAGER)
    run, product, _ = completed_run(db, user)
    body = override_payload(product.id)
    assert client.post(f"/api/forecasts/runs/{run.id}/override", json=body).status_code == 403
    assert client.post(f"/api/forecasts/runs/{run.id}/approve").status_code == 403
    assert client.get("/api/audit-log").status_code == 403


def test_second_approval_is_rejected_and_approval_is_audited(client, planner, db):
    run, _, _ = completed_run(db, planner)
    first = client.post(f"/api/forecasts/runs/{run.id}/approve")
    second = client.post(f"/api/forecasts/runs/{run.id}/approve")
    assert first.status_code == 200
    assert second.status_code == 409
    assert db.query(ForecastApproval).filter_by(run_id=run.id).count() == 1
    assert db.query(AuditLog).filter_by(action="FORECAST_APPROVED", run_id=run.id).count() == 1
