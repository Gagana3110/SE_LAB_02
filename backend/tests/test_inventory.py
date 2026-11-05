import pytest

from app.auth.models import Role
from app.masterdata.models import Product, RawMaterial


@pytest.fixture
def inventory_manager(login_as):
    return login_as(Role.INVENTORY_MANAGER)


@pytest.fixture
def planner(login_as):
    return login_as(Role.DEMAND_PLANNER)


@pytest.fixture
def product(db):
    item = Product(code="P100", name="Widget", unit="each")
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@pytest.fixture
def material(db):
    item = RawMaterial(code="M100", name="Steel", unit="kg")
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def movement(item_type, item_id, movement_type, qty, day="2026-11-01", reference=None):
    return {
        "item_type": item_type,
        "item_id": item_id,
        "movement_type": movement_type,
        "qty": str(qty),
        "movement_date": day,
        "reference": reference,
    }


def test_tc_data_02_receipts_issues_adjustment_and_balance(
    client, inventory_manager, material
):
    path = "/api/inventory/movements"
    receipt = client.post(path, json=movement("raw_material", material.id, "receipt", 100))
    issue = client.post(path, json=movement("raw_material", material.id, "issue", 25))
    adjustment = client.post(path, json=movement("raw_material", material.id, "adjustment", -5))
    assert receipt.status_code == issue.status_code == adjustment.status_code == 201

    response = client.get("/api/inventory/balances", params={
        "item_type": "raw_material", "item_id": material.id
    })
    assert response.status_code == 200
    assert response.json()[0]["on_hand_qty"] == "70.0000"

    movements = client.get(path, params={"item_type": "raw_material"}).json()
    assert [row["movement_type"] for row in movements] == ["receipt", "issue", "adjustment"]


def test_tc_data_02_rejects_issue_larger_than_on_hand(client, inventory_manager, material):
    path = "/api/inventory/movements"
    client.post(path, json=movement("raw_material", material.id, "receipt", 10))
    response = client.post(path, json=movement("raw_material", material.id, "issue", 11))
    assert response.status_code == 400
    balance = client.get("/api/inventory/balances", params={
        "item_type": "raw_material", "item_id": material.id
    }).json()[0]["on_hand_qty"]
    assert balance == "10.0000"


def test_adjustment_cannot_make_stock_negative(client, inventory_manager, material):
    response = client.post(
        "/api/inventory/movements",
        json=movement("raw_material", material.id, "adjustment", -1),
    )
    assert response.status_code == 400


def test_product_and_material_balances_are_separate(client, inventory_manager, product, material):
    path = "/api/inventory/movements"
    client.post(path, json=movement("product", product.id, "receipt", 5))
    client.post(path, json=movement("raw_material", material.id, "receipt", 12))
    rows = client.get("/api/inventory/balances").json()
    balances = {(row["item_type"], row["item_id"]): row["on_hand_qty"] for row in rows}
    assert balances[("product", product.id)] == "5.0000"
    assert balances[("raw_material", material.id)] == "12.0000"


def test_unknown_inventory_item_is_rejected(client, inventory_manager):
    response = client.post(
        "/api/inventory/movements", json=movement("raw_material", 999, "receipt", 2)
    )
    assert response.status_code == 404


def test_market_indicator_create_and_list_tc_data_03(client, planner, product):
    payload = {
        "product_id": product.id,
        "period": "2026-11-01",
        "promotion": True,
        "price_change_pct": "-12.5",
        "holiday_flag": True,
        "trend_index": "1.25",
    }
    created = client.post("/api/market-indicators", json=payload)
    assert created.status_code == 201
    assert created.json()["promotion"] is True
    assert created.json()["price_change_pct"] == "-12.5000"
    listed = client.get("/api/market-indicators", params={"product_id": product.id}).json()
    assert len(listed) == 1
    assert listed[0]["period"] == "2026-11-01"
    assert listed[0]["holiday_flag"] is True
    assert listed[0]["trend_index"] == "1.2500"


def test_market_indicator_duplicate_product_period_returns_409(client, planner, product):
    payload = {"product_id": product.id, "period": "2026-11-01", "promotion": True}
    assert client.post("/api/market-indicators", json=payload).status_code == 201
    assert client.post("/api/market-indicators", json=payload).status_code == 409


def test_market_indicator_rejects_unknown_product(client, planner):
    response = client.post("/api/market-indicators", json={
        "product_id": 999, "period": "2026-11-01"
    })
    assert response.status_code == 404


def test_market_indicator_rejects_price_change_below_minus_100(client, planner, product):
    response = client.post("/api/market-indicators", json={
        "product_id": product.id, "period": "2026-11-01", "price_change_pct": -101
    })
    assert response.status_code == 400


def test_inventory_role_permissions(client, db, login_as, material, product):
    login_as(Role.DEMAND_PLANNER)
    assert client.post(
        "/api/inventory/movements", json=movement("raw_material", material.id, "receipt", 1)
    ).status_code == 403
    assert client.post("/api/market-indicators", json={
        "product_id": product.id, "period": "2026-11-01"
    }).status_code == 201

    login_as(Role.PROCUREMENT_MANAGER)
    assert client.get("/api/inventory/balances").status_code == 200
    assert client.post("/api/market-indicators", json={
        "product_id": product.id, "period": "2026-12-01"
    }).status_code == 403


def test_inventory_reads_require_login(client):
    assert client.get("/api/inventory/movements").status_code == 401
    assert client.get("/api/inventory/balances").status_code == 401
    assert client.get("/api/market-indicators").status_code == 401


def test_admin_can_record_stock_and_market_data(client, login_as, material, product):
    login_as(Role.ADMINISTRATOR)
    assert client.post(
        "/api/inventory/movements", json=movement("raw_material", material.id, "receipt", 3)
    ).status_code == 201
    assert client.post("/api/market-indicators", json={
        "product_id": product.id, "period": "2026-11-01"
    }).status_code == 201
