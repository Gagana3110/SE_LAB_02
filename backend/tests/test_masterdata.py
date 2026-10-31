import pytest

from app.auth.models import Role
from app.masterdata import service
from app.masterdata.models import Product
from app.masterdata.schemas import ItemCreate

ITEM_PATHS = ["/api/products", "/api/materials"]
NON_ADMINS = [r for r in Role if r is not Role.ADMINISTRATOR]


def item(code="P001", **extra):
    return {"code": code, "name": f"Item {code}", "unit": "piece", **extra}


@pytest.fixture
def admin(login_as):
    return login_as(Role.ADMINISTRATOR)


def add(client, path, code):
    response = client.post(path, json=item(code))
    assert response.status_code == 201
    return response.json()


# TC-MD-01: products, raw materials and BOM


@pytest.mark.parametrize("path", ITEM_PATHS)
def test_admin_can_create_and_read_an_item(client, admin, path):
    created = client.post(path, json=item("ab-1", category="Steel"))
    assert created.status_code == 201
    body = created.json()
    assert body["code"] == "AB-1"
    assert body["category"] == "Steel"
    assert body["active"] is True
    assert client.get(f"{path}/{body['id']}").json() == body
    assert client.get(path).json() == [body]


@pytest.mark.parametrize("path", ITEM_PATHS)
def test_duplicate_code_is_rejected(client, admin, path):
    add(client, path, "P001")
    assert client.post(path, json=item("p001")).status_code == 409


@pytest.mark.parametrize("path", ITEM_PATHS)
@pytest.mark.parametrize("bad", [
    {"code": ""}, {"code": "has space"}, {"code": "X" * 33}, {"name": "   "}, {"unit": ""},
])
def test_invalid_fields_are_rejected(client, admin, path, bad):
    assert client.post(path, json={**item(), **bad}).status_code == 400


@pytest.mark.parametrize("path", ITEM_PATHS)
def test_admin_can_edit_an_item(client, admin, path):
    created = add(client, path, "P001")
    response = client.patch(f"{path}/{created['id']}", json={"name": "New name"})
    assert response.status_code == 200
    assert response.json() == {**created, "name": "New name"}


@pytest.mark.parametrize("path", ITEM_PATHS)
def test_editing_to_an_existing_code_is_rejected(client, admin, path):
    add(client, path, "P001")
    second = add(client, path, "P002")
    assert client.patch(f"{path}/{second['id']}", json={"code": "P001"}).status_code == 409
    assert client.get(f"{path}/{second['id']}").json()["code"] == "P002"


@pytest.mark.parametrize("path", ITEM_PATHS)
def test_required_fields_cannot_be_cleared(client, admin, path):
    created = add(client, path, "P001")
    for field in ("code", "name", "unit", "active"):
        response = client.patch(f"{path}/{created['id']}", json={field: None})
        assert response.status_code == 400


@pytest.mark.parametrize("path", ITEM_PATHS)
def test_category_can_be_cleared(client, admin, path):
    created = client.post(path, json=item(category="Steel")).json()
    response = client.patch(f"{path}/{created['id']}", json={"category": None})
    assert response.json()["category"] is None


@pytest.mark.parametrize("path", ITEM_PATHS)
def test_deactivated_item_is_left_out_of_active_list(client, admin, path):
    keep = add(client, path, "P001")
    drop = add(client, path, "P002")
    assert client.patch(f"{path}/{drop['id']}", json={"active": False}).status_code == 200
    active = client.get(path, params={"active_only": True}).json()
    assert [i["id"] for i in active] == [keep["id"]]
    assert len(client.get(path).json()) == 2  # still kept for history


def test_new_forecasts_can_list_only_active_products(client, admin, db):
    add(client, "/api/products", "P001")
    drop = add(client, "/api/products", "P002")
    client.patch(f"/api/products/{drop['id']}", json={"active": False})
    assert [p.code for p in service.list_items(db, Product, active_only=True)] == ["P001"]


@pytest.mark.parametrize("path", ITEM_PATHS)
def test_unknown_item_returns_404(client, admin, path):
    assert client.get(f"{path}/999").status_code == 404
    assert client.patch(f"{path}/999", json={"name": "x"}).status_code == 404


def bom_setup(client):
    product = add(client, "/api/products", "P001")
    steel = add(client, "/api/materials", "M001")
    paint = add(client, "/api/materials", "M002")
    return product, steel, paint


def put_bom(client, product_id, *lines):
    return client.put(f"/api/products/{product_id}/bom", json={"lines": [
        {"material_id": m, "qty_per_unit": q} for m, q in lines]})


def test_bom_can_be_saved_and_read(client, admin):
    product, steel, paint = bom_setup(client)
    response = put_bom(client, product["id"], (steel["id"], 2.5), (paint["id"], 0.25))
    assert response.status_code == 200
    bom = client.get(f"/api/products/{product['id']}/bom").json()
    assert [(line["material"]["code"], line["qty_per_unit"]) for line in bom] == [
        ("M001", 2.5), ("M002", 0.25)]


def test_saving_a_bom_replaces_the_old_one(client, admin):
    product, steel, paint = bom_setup(client)
    put_bom(client, product["id"], (steel["id"], 2), (paint["id"], 1))
    put_bom(client, product["id"], (steel["id"], 5))
    bom = client.get(f"/api/products/{product['id']}/bom").json()
    assert [(line["material"]["code"], line["qty_per_unit"]) for line in bom] == [("M001", 5)]
    put_bom(client, product["id"])
    assert client.get(f"/api/products/{product['id']}/bom").json() == []


@pytest.mark.parametrize("qty", [0, -1, 0.00001])
def test_bom_quantity_must_be_positive_and_precise(client, admin, qty):
    product, steel, _ = bom_setup(client)
    assert put_bom(client, product["id"], (steel["id"], qty)).status_code == 400


def test_material_can_appear_only_once_in_a_bom(client, admin):
    product, steel, _ = bom_setup(client)
    assert put_bom(client, product["id"], (steel["id"], 1), (steel["id"], 2)).status_code == 400


def test_unknown_or_inactive_material_is_rejected_and_old_bom_kept(client, admin):
    product, steel, paint = bom_setup(client)
    put_bom(client, product["id"], (steel["id"], 2))
    client.patch(f"/api/materials/{paint['id']}", json={"active": False})
    assert put_bom(client, product["id"], (paint["id"], 1)).status_code == 422
    assert put_bom(client, product["id"], (999, 1)).status_code == 422
    bom = client.get(f"/api/products/{product['id']}/bom").json()
    assert [line["material"]["code"] for line in bom] == ["M001"]


def test_bom_of_unknown_product_returns_404(client, admin):
    assert client.get("/api/products/999/bom").status_code == 404
    assert client.put("/api/products/999/bom", json={"lines": []}).status_code == 404


# TC-Sec-03: every role can read, only Administrators can change


@pytest.mark.parametrize("role", NON_ADMINS)
def test_other_roles_can_read_but_not_write(client, db, login_as, role):
    product = service.create_item(db, Product, ItemCreate(**item("P001")))
    login_as(role)
    assert client.get("/api/products").status_code == 200
    assert client.get(f"/api/products/{product.id}/bom").status_code == 200
    assert client.post("/api/products", json=item("P002")).status_code == 403
    assert client.patch(f"/api/products/{product.id}", json={"name": "x"}).status_code == 403
    assert client.put(f"/api/products/{product.id}/bom", json={"lines": []}).status_code == 403
    assert client.post("/api/materials", json=item("M001")).status_code == 403


@pytest.mark.parametrize("path", ITEM_PATHS)
def test_reads_need_a_session(client, path):
    assert client.get(path).status_code == 401
    assert client.get(f"{path}/1").status_code == 401
    assert client.get("/api/products/1/bom").status_code == 401
