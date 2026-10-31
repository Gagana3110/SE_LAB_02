import math
from datetime import date

import numpy as np
import pytest
from kombu.exceptions import OperationalError
from sqlalchemy import select

from app.auth.models import Role
from app.forecasting import engine, service
from app.forecasting.models import DONE, FAILED, QUEUED, ForecastLine, ForecastRun
from app.forecasting.schemas import RunCreate
from app.forecasting.tasks import celery_app, run_forecast
from app.masterdata.models import Product
from app.sales.models import SalesRecord


def month(offset: int, year: int = 2023) -> date:
    return date(year + offset // 12, offset % 12 + 1, 1)


def seasonal_demand(months: int = 36) -> list[tuple[date, int]]:
    """A known trend and yearly season, with no noise, so accuracy can be checked."""
    return [(month(t), round((500 + 5 * t) * (1 + 0.3 * math.sin(2 * math.pi * t / 12))))
            for t in range(months)]


# Calculations


def test_moving_average_is_the_mean_of_the_last_three_periods():
    records = [(month(0), 10), (month(1), 20), (month(2), 30), (month(3), 40)]
    model, points = engine.forecast_product(records, 2, engine.MONTH, ["MA"])
    assert model == "MA"
    assert [p.forecast for p in points] == [30.0, 30.0]
    assert [p.period for p in points] == [month(4), month(5)]


def test_regions_are_added_together():
    series = engine.demand_series([(month(0), 10), (month(0), 5), (month(1), 7)], engine.MONTH)
    assert series.tolist() == [15, 7]


def test_months_without_sales_count_as_zero():
    series = engine.demand_series([(month(0), 10), (month(3), 7)], engine.MONTH)
    assert series.tolist() == [10, 0, 0, 7]


def test_weeks_are_grouped_from_monday():
    records = [(date(2026, 1, 5), 1), (date(2026, 1, 11), 2), (date(2026, 1, 12), 4)]
    series = engine.demand_series(records, engine.WEEK)
    assert series.tolist() == [3, 4]
    assert series.index[0].date() == date(2026, 1, 5)


def test_extreme_value_is_capped_but_normal_values_are_kept():
    values = [100.0] * 20 + [10000.0]
    index = engine.demand_series([(month(i), 1) for i in range(21)], engine.MONTH).index
    cleaned = engine.clean(engine.pd.Series(values, index=index))
    assert cleaned.iloc[0] == 100
    assert cleaned.iloc[-1] < 10000


def test_very_short_series_is_not_cleaned():
    series = engine.demand_series([(month(0), 1), (month(1), 500)], engine.MONTH)
    assert engine.clean(series).tolist() == [1, 500]


def test_holt_winters_is_used_with_two_seasons_of_history():
    assert engine.forecast_product(seasonal_demand(24), 3, engine.MONTH, ["MA", "HW"])[0] == "HW"


def test_short_history_uses_moving_average():
    assert engine.forecast_product(seasonal_demand(23), 3, engine.MONTH, ["MA", "HW"])[0] == "MA"
    assert engine.forecast_product(seasonal_demand(23), 3, engine.MONTH, ["HW"])[0] == "MA"


def test_user_can_choose_moving_average_only():
    assert engine.forecast_product(seasonal_demand(36), 3, engine.MONTH, ["MA"])[0] == "MA"


def test_holt_winters_follows_the_season_better_than_moving_average():
    train, future = seasonal_demand(36), [q for _, q in seasonal_demand(48)[36:]]
    _, hw = engine.forecast_product(train, 12, engine.MONTH, ["HW"])
    _, ma = engine.forecast_product(train, 12, engine.MONTH, ["MA"])
    def error(points):
        return np.mean([abs(p.forecast - actual) / actual for p, actual in zip(points, future)])
    assert error(hw) < 0.05
    assert error(hw) < error(ma) / 2


def test_holt_winters_handles_months_with_zero_sales():
    records = seasonal_demand(36)
    records[5] = (records[5][0], 0)
    model, points = engine.forecast_product(records, 3, engine.MONTH, ["HW"])
    assert model == "HW"
    assert all(p.forecast > 0 for p in points)


def test_holt_winters_refuses_too_little_history():
    with pytest.raises(ValueError):
        engine.HoltWinters(12).fit(engine.demand_series(seasonal_demand(23), engine.MONTH))


def test_results_are_plain_numbers_the_database_can_store():
    _, points = engine.forecast_product(seasonal_demand(36), 2, engine.MONTH, ["HW"])
    for field in ("forecast", "lower80", "upper80", "lower95", "upper95"):
        assert type(getattr(points[0], field)) is float


def test_failed_model_falls_back_to_moving_average(monkeypatch):
    def broken_fit(self, series):
        raise np.linalg.LinAlgError("no solution")

    monkeypatch.setattr(engine.HoltWinters, "fit", broken_fit)
    assert engine.forecast_product(seasonal_demand(36), 3, engine.MONTH, ["HW"])[0] == "MA"


def test_unusable_holt_winters_values_are_rejected():
    model = engine.HoltWinters(12).fit(engine.demand_series(seasonal_demand(36), engine.MONTH))

    class Broken:
        @staticmethod
        def forecast(horizon):
            return np.full(horizon, np.nan)

    model._fitted = Broken()
    with pytest.raises(ValueError):
        model.predict(3)


@pytest.mark.parametrize("allowed", [["MA"], ["HW"]])
def test_intervals_contain_the_forecast_and_widen_over_time(allowed):
    _, points = engine.forecast_product(seasonal_demand(36), 6, engine.MONTH, allowed)
    for p in points:
        assert 0 <= p.lower95 <= p.lower80 <= p.forecast <= p.upper80 <= p.upper95
    widths = [p.upper95 - p.lower95 for p in points]
    assert widths == sorted(widths) and widths[-1] > widths[0]


def test_forecast_and_bounds_are_never_negative():
    records = [(month(t), max(0, 100 - 30 * t)) for t in range(5)] + [(month(5), 0)]
    _, points = engine.forecast_product(records, 3, engine.MONTH, ["MA"])
    assert all(p.forecast >= 0 and p.lower95 >= 0 for p in points)


def test_single_period_of_history_still_gives_a_forecast():
    _, points = engine.forecast_product([(month(0), 40)], 2, engine.MONTH, ["MA", "HW"])
    assert [p.forecast for p in points] == [40.0, 40.0]


# API and background job


@pytest.fixture(autouse=True)
def run_jobs_inline():
    celery_app.conf.task_always_eager = True
    yield
    celery_app.conf.task_always_eager = False


@pytest.fixture
def planner(login_as):
    return login_as(Role.DEMAND_PLANNER)


def add_product(db, code="P001", records=None, active=True):
    product = Product(code=code, name=code, unit="piece", active=active)
    db.add(product)
    db.flush()
    for period, quantity in records if records is not None else seasonal_demand():
        db.add(SalesRecord(product_id=product.id, period=period, quantity=quantity, region=""))
    db.commit()
    return product


def start(client, ids, horizon=6, **extra):
    return client.post("/api/forecasts/runs", json={"productIds": ids, "horizon": horizon, **extra})


def test_run_produces_a_forecast_for_the_full_horizon(client, planner, db):
    products = [add_product(db, f"P{i:03d}") for i in range(3)]
    response = start(client, [p.id for p in products], horizon=6)
    assert response.status_code == 202
    run_id = response.json()["runId"]
    body = client.get(f"/api/forecasts/runs/{run_id}").json()
    assert body["status"] == DONE
    assert body["error"] is None
    assert [p["code"] for p in body["products"]] == ["P000", "P001", "P002"]
    for product in body["products"]:
        assert product["model"] == "HW"
        assert len(product["points"]) == 6
        assert product["points"][0]["period"] == "2026-01-01"
        assert set(product["points"][0]) == {
            "period", "forecast", "lower80", "upper80", "lower95", "upper95"}


def test_all_means_every_active_product(client, planner, db):
    keep = add_product(db, "P001")
    add_product(db, "P002", active=False)
    run_id = start(client, "ALL").json()["runId"]
    products = client.get(f"/api/forecasts/runs/{run_id}").json()["products"]
    assert [p["productId"] for p in products] == [keep.id]


def test_weekly_forecast(client, planner, db):
    start_day = date(2026, 1, 5)
    records = [(date.fromordinal(start_day.toordinal() + 7 * i), 10 + i) for i in range(10)]
    product = add_product(db, records=records)
    run_id = start(client, [product.id], horizon=4, granularity="WEEK").json()["runId"]
    points = client.get(f"/api/forecasts/runs/{run_id}").json()["products"][0]["points"]
    assert [p["period"] for p in points][:2] == ["2026-03-16", "2026-03-23"]
    assert len(points) == 4


def test_product_without_sales_is_skipped_with_a_reason(client, planner, db):
    good, empty = add_product(db, "P001"), add_product(db, "P002", records=[])
    run_id = start(client, [good.id, empty.id]).json()["runId"]
    body = client.get(f"/api/forecasts/runs/{run_id}").json()
    assert body["status"] == DONE
    assert body["skipped"] == [{"productId": empty.id, "reason": "No sales history"}]
    assert [p["productId"] for p in body["products"]] == [good.id]


def test_run_fails_with_a_reason_when_no_product_has_sales(client, planner, db):
    empty = add_product(db, records=[])
    run_id = start(client, [empty.id]).json()["runId"]
    body = client.get(f"/api/forecasts/runs/{run_id}").json()
    assert body["status"] == FAILED
    assert "sales history" in body["error"]


def test_unexpected_failure_marks_the_run_failed_without_details(client, planner, db, monkeypatch):
    product = add_product(db)

    def crash(*_):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(engine, "forecast_product", crash)
    run_id = start(client, [product.id]).json()["runId"]
    body = client.get(f"/api/forecasts/runs/{run_id}").json()
    assert body["status"] == FAILED
    assert body["error"] == "The forecast could not be completed"
    db.expire_all()
    assert db.scalars(select(ForecastLine)).all() == []


def test_queue_outage_returns_503_and_fails_the_run(client, planner, db, monkeypatch):
    product = add_product(db)

    def down(_):
        raise OperationalError("redis is down")

    monkeypatch.setattr(run_forecast, "delay", down)
    assert start(client, [product.id]).status_code == 503
    db.expire_all()
    assert db.scalar(select(ForecastRun.status)) == FAILED


def test_second_run_for_the_same_products_is_refused_while_one_is_active(client, planner, db):
    product = add_product(db)
    data = RunCreate(product_ids=[product.id], horizon=3)
    service.create_run(db, planner.id, data)  # stays QUEUED, since no job was started
    assert start(client, [product.id]).status_code == 409
    other = add_product(db, "P002")
    assert start(client, [other.id]).status_code == 202


def test_a_stuck_run_stops_blocking_after_30_minutes(client, planner, db):
    product = add_product(db)
    run = service.create_run(db, planner.id, RunCreate(product_ids=[product.id], horizon=3))
    run.created_at = run.created_at - service.STALE_AFTER * 2
    db.commit()
    assert start(client, [product.id]).status_code == 202


def test_job_ignores_finished_or_unknown_runs(planner, db):
    product = add_product(db)
    run = service.create_run(db, planner.id, RunCreate(product_ids=[product.id], horizon=3))
    assert run.status == QUEUED
    service.execute_run(db, run.id)
    assert run.status == DONE
    count = len(db.scalars(select(ForecastLine)).all())
    service.execute_run(db, run.id)
    service.execute_run(db, 999)
    assert len(db.scalars(select(ForecastLine)).all()) == count


@pytest.mark.parametrize("body", [
    {"productIds": [1], "horizon": 0},
    {"productIds": [1], "horizon": 13},
    {"productIds": [1], "horizon": 3, "granularity": "WEEK"},
    {"productIds": [1], "horizon": 53, "granularity": "WEEK"},
    {"productIds": [1], "horizon": 3, "granularity": "DAY"},
    {"productIds": [], "horizon": 3},
    {"productIds": "SOME", "horizon": 3},
    {"productIds": [1], "horizon": 3, "models": []},
    {"productIds": [1], "horizon": 3, "models": ["SARIMAX"]},
])
def test_invalid_requests_are_rejected(client, planner, body):
    assert client.post("/api/forecasts/runs", json=body).status_code == 400


def test_unknown_or_inactive_products_are_rejected(client, planner, db):
    inactive = add_product(db, active=False)
    assert start(client, [999]).status_code == 422
    assert start(client, [inactive.id]).status_code == 422


def test_all_with_no_products_is_rejected(client, planner):
    assert start(client, "ALL").status_code == 422


def test_chart_data_has_history_and_forecast(client, planner, db):
    product = add_product(db)
    run_id = start(client, [product.id]).json()["runId"]
    chart = client.get(f"/api/forecasts/runs/{run_id}/products/{product.id}").json()
    assert chart["code"] == "P001"
    assert len(chart["history"]) == 36
    assert chart["history"][0] == {"period": "2023-01-01", "actual": 500.0}
    assert len(chart["points"]) == 6


def test_chart_history_is_empty_without_sales(db):
    product = add_product(db, records=[])
    assert service.actual_history(db, product.id, engine.MONTH) == []


def test_unknown_run_or_product_returns_404(client, planner, db):
    product = add_product(db)
    run_id = start(client, [product.id]).json()["runId"]
    assert client.get("/api/forecasts/runs/999").status_code == 404
    assert client.get(f"/api/forecasts/runs/999/products/{product.id}").status_code == 404
    assert client.get(f"/api/forecasts/runs/{run_id}/products/999").status_code == 404


@pytest.mark.parametrize("role", [r for r in Role if r is not Role.DEMAND_PLANNER])
def test_only_planners_can_start_a_run_but_others_can_read(client, db, login_as, make_user, role):
    product = add_product(db)
    owner = make_user(Role.DEMAND_PLANNER)
    run = service.create_run(db, owner.id, RunCreate(product_ids=[product.id], horizon=3))
    service.execute_run(db, run.id)
    login_as(role)
    assert start(client, [product.id]).status_code == 403
    assert client.get(f"/api/forecasts/runs/{run.id}").status_code == 200


def test_forecast_endpoints_need_a_session(client):
    assert start(client, [1]).status_code == 401
    assert client.get("/api/forecasts/runs/1").status_code == 401
    assert client.get("/api/forecasts/runs/1/products/1").status_code == 401
