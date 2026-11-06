import pytest

from app import hardening
from app.auth.models import Role
from app.config import settings
from app.hardening import SlidingWindowLimiter
from tests.conftest import PASSWORD


def login(client, email="nobody@dfs-demo.com", password="wrong-password", **headers):
    return client.post("/api/auth/login", json={"email": email, "password": password},
                       headers=headers)


# TC-Sec-06: rate limiting


def test_login_is_limited_to_10_attempts_per_minute(client):
    for _ in range(10):
        assert login(client).status_code == 401
    response = login(client)
    assert response.status_code == 429
    assert response.json()["error"] == {
        "code": 429, "message": "Too many requests. Please wait and try again."}
    assert response.json()["requestId"] == response.headers["x-request-id"]
    assert 1 <= int(response.headers["retry-after"]) <= 60


def test_a_limited_user_cannot_log_in_even_with_the_right_password(client, make_user):
    user = make_user(Role.DEMAND_PLANNER)
    for _ in range(10):
        login(client)
    assert login(client, user.email, PASSWORD).status_code == 429


def test_api_calls_are_limited_per_user(client, login_as, monkeypatch):
    monkeypatch.setattr(settings, "api_rate_per_minute", 5)
    login_as(Role.ADMINISTRATOR)
    for _ in range(5):
        assert client.get("/api/products").status_code == 200
    assert client.get("/api/products").status_code == 429


def test_each_user_has_their_own_api_limit(client, make_user, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setattr(settings, "api_rate_per_minute", 3)
    first, second = TestClient(app), TestClient(app)
    for role, browser in ((Role.ADMINISTRATOR, first), (Role.DEMAND_PLANNER, second)):
        user = make_user(role)
        assert login(browser, user.email, PASSWORD).status_code == 200
    for _ in range(3):
        first.get("/api/products")
    assert first.get("/api/products").status_code == 429
    assert second.get("/api/products").status_code == 200


def test_anonymous_api_calls_are_limited_by_address(client, monkeypatch):
    monkeypatch.setattr(settings, "api_rate_per_minute", 2)
    for _ in range(2):
        assert client.get("/api/products").status_code == 401
    assert client.get("/api/products").status_code == 429


def test_health_checks_are_never_limited(client, monkeypatch):
    monkeypatch.setattr(settings, "api_rate_per_minute", 1)
    for path in ["/health", "/api/health"] * 3:
        assert client.get(path).status_code == 200


def test_forwarded_address_is_used_only_when_trusted(client, monkeypatch):
    for _ in range(10):
        login(client, **{"X-Real-IP": "10.0.0.1"})
    # Not trusted: the header is ignored, so every attempt came from the same address.
    assert login(client, **{"X-Real-IP": "10.0.0.2"}).status_code == 429

    hardening.limiter.reset()
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    for _ in range(10):
        login(client, **{"X-Real-IP": "10.0.0.1"})
    assert login(client, **{"X-Real-IP": "10.0.0.1"}).status_code == 429
    assert login(client, **{"X-Real-IP": "10.0.0.2"}).status_code == 401


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_limit_resets_after_the_window():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(window=60, clock=clock)
    assert [limiter.hit("k", 2) for _ in range(2)] == [0.0, 0.0]
    assert limiter.hit("k", 2) == pytest.approx(60)
    clock.now += 30
    assert limiter.hit("k", 2) == pytest.approx(30)
    clock.now += 31
    assert limiter.hit("k", 2) == 0.0


def test_old_keys_are_pruned():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(window=60, clock=clock)
    limiter.hit("old", 5)
    clock.now += 61
    limiter.hit("new", 5)
    limiter.prune()
    assert set(limiter._hits) == {"new"}


def test_pruning_runs_when_many_visitors_are_tracked(client, monkeypatch):
    calls = []
    monkeypatch.setattr(hardening.limiter, "prune", lambda: calls.append(1))
    monkeypatch.setattr(hardening.limiter, "_hits", {str(i): None for i in range(10_001)})
    monkeypatch.setattr(hardening.limiter, "hit", lambda key, limit: 0.0)
    client.get("/api/products")
    assert calls == [1]


# Security headers


def test_api_responses_carry_security_headers(client):
    headers = client.get("/api/health").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["content-security-policy"] == hardening.API_CSP
    assert "strict-transport-security" not in headers


def test_error_and_limited_responses_also_carry_headers(client, monkeypatch):
    assert client.get("/api/products").headers["x-frame-options"] == "DENY"
    monkeypatch.setattr(settings, "api_rate_per_minute", 0)
    assert client.get("/api/products").headers["x-frame-options"] == "DENY"


def test_https_deployments_send_strict_transport_security(client, monkeypatch):
    monkeypatch.setattr(settings, "cookie_secure", True)
    assert "max-age=31536000" in client.get("/api/health").headers["strict-transport-security"]


def test_api_docs_page_still_works(client):
    response = client.get("/docs")
    assert response.status_code == 200
    assert "content-security-policy" not in response.headers
    assert response.headers["x-content-type-options"] == "nosniff"
