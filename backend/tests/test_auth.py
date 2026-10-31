from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import security, service
from app.auth.deps import SESSION_COOKIE
from app.auth.models import Role, User
from app.config import Settings, settings
from app.main import app
from tests.conftest import PASSWORD

ALL_ROLES = list(Role)
GENERIC_ERROR = "Invalid email or password, or the account is temporarily locked"


def attempt(client, email, password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


# TC-Auth-01: login and session timeout


def test_valid_login_starts_a_session(client, make_user):
    user = make_user(Role.DEMAND_PLANNER)
    response = attempt(client, user.email)
    assert response.status_code == 200
    assert response.json() == {"id": user.id, "email": user.email, "role": "demand_planner"}
    assert client.get("/api/auth/me").json()["email"] == user.email


def test_session_cookie_is_protected(client, make_user):
    cookie = attempt(client, make_user(Role.DEMAND_PLANNER).email).headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie


def test_email_is_case_insensitive(client, make_user):
    user = make_user(Role.DEMAND_PLANNER)
    assert attempt(client, user.email.upper()).status_code == 200


def test_wrong_password_and_unknown_email_give_the_same_error(client, make_user):
    user = make_user(Role.DEMAND_PLANNER)
    wrong = attempt(client, user.email, "wrong-password")
    unknown = attempt(client, "nobody@dfs-demo.com")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"] == GENERIC_ERROR


def test_requests_without_a_session_are_rejected(client):
    assert client.get("/api/auth/me").status_code == 401


def test_expired_session_is_rejected(client, make_user):
    user = make_user(Role.DEMAND_PLANNER)
    client.cookies.set(SESSION_COOKIE, security.create_token(user.id, minutes=-1))
    assert client.get("/api/auth/me").status_code == 401


def test_tampered_token_is_rejected(client, make_user):
    token = security.create_token(make_user(Role.DEMAND_PLANNER).id)
    client.cookies.set(SESSION_COOKIE, token[:-2] + "xx")
    assert client.get("/api/auth/me").status_code == 401


def test_activity_renews_the_session(client, make_user):
    attempt(client, make_user(Role.DEMAND_PLANNER).email)
    cookie = client.get("/api/auth/me").headers["set-cookie"].lower()
    assert f"max-age={settings.session_minutes * 60}" in cookie


def test_logout_ends_the_session(client, make_user):
    attempt(client, make_user(Role.DEMAND_PLANNER).email)
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


# TC-Auth-02 and TC-Sec-03: role-based access, enforced on the server


@pytest.mark.parametrize("role", [r for r in ALL_ROLES if r is not Role.ADMINISTRATOR])
def test_other_roles_cannot_use_admin_endpoints(client, login_as, role):
    login_as(role)
    assert client.get("/api/users").status_code == 403
    new_user = {"email": "x@dfs-demo.com", "password": PASSWORD, "role": "administrator"}
    assert client.post("/api/users", json=new_user).status_code == 403


def test_admin_endpoints_need_a_session(client):
    assert client.get("/api/users").status_code == 401


@pytest.mark.parametrize("role", ALL_ROLES)
def test_admin_can_create_a_user_of_each_role(client, login_as, role):
    login_as(Role.ADMINISTRATOR)
    body = {"email": "new@dfs-demo.com", "password": PASSWORD, "role": role.value}
    response = client.post("/api/users", json=body)
    assert response.status_code == 201
    assert response.json()["role"] == role.value
    assert "new@dfs-demo.com" in [u["email"] for u in client.get("/api/users").json()]


def test_duplicate_email_is_rejected(client, login_as):
    admin = login_as(Role.ADMINISTRATOR)
    body = {"email": admin.email, "password": PASSWORD, "role": "demand_planner"}
    assert client.post("/api/users", json=body).status_code == 409


def test_short_password_is_rejected_without_echoing_it(client, login_as):
    login_as(Role.ADMINISTRATOR)
    body = {"email": "new@dfs-demo.com", "password": "short77", "role": "demand_planner"}
    response = client.post("/api/users", json=body)
    assert response.status_code == 400
    assert response.json()["error"]["details"][0]["field"] == "password"
    assert "short77" not in response.text


# TC-Sec-02: password storage and lockout


def test_passwords_are_stored_only_as_argon2_hashes(db, make_user):
    make_user(Role.DEMAND_PLANNER)
    stored = db.scalar(select(User.password_hash))
    assert stored.startswith("$argon2")
    assert PASSWORD not in stored


def test_account_locks_after_five_failures(client, make_user):
    user = make_user(Role.DEMAND_PLANNER)
    for _ in range(5):
        assert attempt(client, user.email, "wrong-password").status_code == 401
    # Even the right password is refused while locked.
    response = attempt(client, user.email)
    assert response.status_code == 401
    assert response.json()["error"]["message"] == GENERIC_ERROR


def test_four_failures_do_not_lock(client, make_user):
    user = make_user(Role.DEMAND_PLANNER)
    for _ in range(4):
        attempt(client, user.email, "wrong-password")
    assert attempt(client, user.email).status_code == 200


def test_success_resets_the_failure_count(client, make_user):
    user = make_user(Role.DEMAND_PLANNER)
    for _ in range(4):
        attempt(client, user.email, "wrong-password")
    attempt(client, user.email)
    for _ in range(4):
        attempt(client, user.email, "wrong-password")
    assert attempt(client, user.email).status_code == 200


def test_lock_expires_after_fifteen_minutes(client, db, make_user):
    user = make_user(Role.DEMAND_PLANNER)
    for _ in range(5):
        attempt(client, user.email, "wrong-password")
    stored = db.get(User, user.id)
    db.refresh(stored)
    assert stored.locked_until is not None
    stored.locked_until = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    assert attempt(client, user.email).status_code == 200


# Error format and first administrator


def test_errors_use_the_standard_format(client):
    response = client.get("/api/auth/me")
    assert response.json()["error"] == {"code": 401, "message": "Not authenticated"}
    assert response.json()["requestId"] == response.headers["x-request-id"]


def test_first_admin_is_created_once_from_configuration(db, monkeypatch):
    monkeypatch.setattr(settings, "admin_email", "Boss@dfs-demo.com")
    monkeypatch.setattr(settings, "admin_password", PASSWORD)
    service.bootstrap_admin(db)
    service.bootstrap_admin(db)
    assert [(u.email, u.role) for u in service.list_users(db)] == [
        ("boss@dfs-demo.com", Role.ADMINISTRATOR)]


def test_no_admin_is_created_without_configuration(db, monkeypatch):
    monkeypatch.setattr(settings, "admin_email", "")
    service.bootstrap_admin(db)
    assert service.list_users(db) == []


def test_app_startup_creates_tables_and_admin(db, monkeypatch):
    monkeypatch.setattr(settings, "admin_email", "boss@dfs-demo.com")
    monkeypatch.setattr(settings, "admin_password", PASSWORD)
    with TestClient(app) as started:
        assert attempt(started, "boss@dfs-demo.com").status_code == 200


def test_missing_jwt_secret_gets_a_random_value():
    first, second = Settings(jwt_secret=""), Settings(jwt_secret="")
    assert first.jwt_secret and first.jwt_secret != second.jwt_secret
    assert Settings(jwt_secret="configured").jwt_secret == "configured"
