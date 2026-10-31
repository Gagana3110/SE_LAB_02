import pytest

from app.auth.models import Role
from app.masterdata.models import RawMaterial
from app.suppliers.models import Supplier


def supplier(code="S01", **extra):
    return {"code": code, "name": f"Supplier {code}", "lead_time_days": 7, "moq": 100,
            "unit_price": 12.5, "monthly_capacity": 5000, "reliability_pct": 90, **extra}


@pytest.fixture
def admin(login_as):
    return login_as(Role.ADMINISTRATOR)


@pytest.fixture
def material(db):
    item = RawMaterial(code="M001", name="Steel", unit="kg")
    db.add(item)
    db.commit()
    return item


def add(client, code="S01", **extra):
    response = client.post("/api/suppliers", json=supplier(code, **extra))
    assert response.status_code == 201
    return response.json()


# TC-MD-02: supplier management


def test_admin_can_create_and_read_a_supplier(client, admin):
    created = add(client, "s01")
    assert created["code"] == "S01"
    assert created["unit_price"] == 12.5
    assert created["active"] is True
    assert client.get(f"/api/suppliers/{created['id']}").json() == created
    assert client.get("/api/suppliers").json() == [created]


@pytest.mark.parametrize("bad", [
    {"lead_time_days": 0}, {"lead_time_days": 3651}, {"moq": 0}, {"unit_price": 0},
    {"unit_price": -1}, {"unit_price": 1.234}, {"monthly_capacity": 0},
    {"reliability_pct": -1}, {"reliability_pct": 101}, {"code": "has space"}, {"name": " "},
])
def test_invalid_values_are_rejected_with_a_field_error(client, admin, bad):
    response = client.post("/api/suppliers", json={**supplier(), **bad})
    assert response.status_code == 400
    assert response.json()["error"]["details"][0]["field"] == next(iter(bad))


def test_duplicate_code_is_rejected(client, admin):
    add(client, "S01")
    assert client.post("/api/suppliers", json=supplier("s01")).status_code == 409


def test_edits_are_saved(client, admin):
    created = add(client)
    response = client.patch(f"/api/suppliers/{created['id']}",
                            json={"lead_time_days": 14, "unit_price": 9.99})
    assert response.status_code == 200
    assert response.json() == {**created, "lead_time_days": 14, "unit_price": 9.99}


def test_edit_cannot_set_invalid_or_empty_values(client, admin):
    created = add(client)
    assert client.patch(f"/api/suppliers/{created['id']}", json={"moq": 0}).status_code == 400
    assert client.patch(f"/api/suppliers/{created['id']}", json={"moq": None}).status_code == 400
    assert client.get(f"/api/suppliers/{created['id']}").json() == created


def test_editing_to_an_existing_code_is_rejected(client, admin):
    add(client, "S01")
    second = add(client, "S02")
    assert client.patch(f"/api/suppliers/{second['id']}", json={"code": "S01"}).status_code == 409


def test_active_only_list_leaves_out_deactivated_suppliers(client, admin):
    keep = add(client, "S01")
    drop = add(client, "S02")
    client.patch(f"/api/suppliers/{drop['id']}", json={"active": False})
    active = client.get("/api/suppliers", params={"active_only": True}).json()
    assert [s["id"] for s in active] == [keep["id"]]
    assert len(client.get("/api/suppliers").json()) == 2


def test_unknown_supplier_returns_404(client, admin):
    assert client.get("/api/suppliers/999").status_code == 404
    assert client.patch("/api/suppliers/999", json={"moq": 5}).status_code == 404


# TC-MD-03: material-supplier links


def put_links(client, material_id, *links):
    return client.put(f"/api/materials/{material_id}/suppliers", json={"links": [
        {"supplier_id": s, "preferred": p} for s, p in links]})


def test_material_can_have_many_suppliers_with_one_preferred(client, admin, material):
    a, b, c = add(client, "S01"), add(client, "S02"), add(client, "S03")
    response = put_links(client, material.id, (a["id"], False), (b["id"], True), (c["id"], False))
    assert response.status_code == 200
    links = client.get(f"/api/materials/{material.id}/suppliers").json()
    assert [(link["supplier"]["code"], link["preferred"]) for link in links] == [
        ("S02", True), ("S01", False), ("S03", False)]


def test_saving_links_replaces_the_old_ones(client, admin, material):
    a, b = add(client, "S01"), add(client, "S02")
    put_links(client, material.id, (a["id"], True), (b["id"], False))
    put_links(client, material.id, (b["id"], True))
    links = client.get(f"/api/materials/{material.id}/suppliers").json()
    assert [link["supplier"]["code"] for link in links] == ["S02"]
    assert put_links(client, material.id).json() == []


@pytest.mark.parametrize("preferred", [(False, False), (True, True)])
def test_exactly_one_supplier_must_be_preferred(client, admin, material, preferred):
    a, b = add(client, "S01"), add(client, "S02")
    response = put_links(client, material.id, (a["id"], preferred[0]), (b["id"], preferred[1]))
    assert response.status_code == 400


def test_supplier_can_be_linked_only_once(client, admin, material):
    a = add(client)
    assert put_links(client, material.id, (a["id"], True), (a["id"], False)).status_code == 400


def test_unknown_or_inactive_supplier_is_rejected_and_old_links_kept(client, admin, material):
    a, b = add(client, "S01"), add(client, "S02")
    put_links(client, material.id, (a["id"], True))
    client.patch(f"/api/suppliers/{b['id']}", json={"active": False})
    assert put_links(client, material.id, (b["id"], True)).status_code == 422
    assert put_links(client, material.id, (999, True)).status_code == 422
    links = client.get(f"/api/materials/{material.id}/suppliers").json()
    assert [link["supplier"]["code"] for link in links] == ["S01"]


def test_links_of_unknown_material_return_404(client, admin):
    assert client.get("/api/materials/999/suppliers").status_code == 404
    assert client.put("/api/materials/999/suppliers", json={"links": []}).status_code == 404


def gaps(client):
    return [m["code"] for m in client.get("/api/purchasing/materials-without-supplier").json()]


def test_material_without_active_supplier_is_flagged(client, admin, material):
    assert gaps(client) == ["M001"]
    a = add(client)
    put_links(client, material.id, (a["id"], True))
    assert gaps(client) == []
    client.patch(f"/api/suppliers/{a['id']}", json={"active": False})
    assert gaps(client) == ["M001"]


def test_inactive_material_is_not_flagged(client, admin, db, material):
    material.active = False
    db.commit()
    assert gaps(client) == []


# TC-Sec-03: prices are visible only to the roles that buy


@pytest.mark.parametrize("role", [Role.DEMAND_PLANNER, Role.INVENTORY_MANAGER])
def test_other_roles_cannot_see_suppliers(client, db, login_as, material, role):
    item = Supplier(**supplier(), active=True)
    db.add(item)
    db.commit()
    login_as(role)
    assert client.get("/api/suppliers").status_code == 403
    assert client.get(f"/api/suppliers/{item.id}").status_code == 403
    assert client.get(f"/api/materials/{material.id}/suppliers").status_code == 403
    assert client.get("/api/purchasing/materials-without-supplier").status_code == 403


def test_procurement_can_read_but_not_change(client, db, login_as, material):
    item = Supplier(**supplier(), active=True)
    db.add(item)
    db.commit()
    login_as(Role.PROCUREMENT_MANAGER)
    assert client.get("/api/suppliers").status_code == 200
    assert client.get(f"/api/materials/{material.id}/suppliers").status_code == 200
    assert client.get("/api/purchasing/materials-without-supplier").status_code == 200
    assert client.post("/api/suppliers", json=supplier("S02")).status_code == 403
    assert client.patch(f"/api/suppliers/{item.id}", json={"moq": 5}).status_code == 403
    assert put_links(client, material.id).status_code == 403


def test_reads_need_a_session(client):
    assert client.get("/api/suppliers").status_code == 401
    assert client.get("/api/materials/1/suppliers").status_code == 401
    assert client.get("/api/purchasing/materials-without-supplier").status_code == 401
