import re
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.auth.models import PasswordResetToken, Role
from tests.conftest import PASSWORD

NEW_PASSWORD = "a-brand-new-password"


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr("app.auth.service.send_email",
                        lambda to, subject, body: sent.append((to, subject, body)))
    return sent


def token_in(outbox) -> str:
    return re.search(r"token=([\w-]+)", outbox[-1][2]).group(1)


def ask(client, email):
    return client.post("/api/auth/password-reset/request", json={"email": email})


def confirm(client, token, password=NEW_PASSWORD):
    return client.post("/api/auth/password-reset/confirm",
                       json={"token": token, "new_password": password})


def log_in(client, email, password):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_link_works_once(client, make_user, outbox):
    user = make_user(Role.DEMAND_PLANNER)
    assert ask(client, user.email).status_code == 202
    assert len(outbox) == 1 and outbox[0][0] == user.email
    token = token_in(outbox)
    assert confirm(client, token).status_code == 204
    assert log_in(client, user.email, NEW_PASSWORD).status_code == 200
    assert log_in(client, user.email, PASSWORD).status_code == 401
    assert confirm(client, token, "another-password-1").status_code == 400  # reused link


def test_expired_link_is_rejected(client, db, make_user, outbox):
    user = make_user(Role.DEMAND_PLANNER)
    ask(client, user.email)
    record = db.scalar(select(PasswordResetToken))
    record.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    assert confirm(client, token_in(outbox)).status_code == 400
    assert log_in(client, user.email, PASSWORD).status_code == 200  # password unchanged


def test_link_lasts_30_minutes_and_token_is_stored_hashed(client, db, make_user, outbox):
    user = make_user(Role.DEMAND_PLANNER)
    ask(client, user.email)
    record = db.scalar(select(PasswordResetToken))
    left = record.expires_at.replace(tzinfo=UTC) - datetime.now(UTC)
    assert timedelta(minutes=29) < left <= timedelta(minutes=30)
    assert record.token_hash != token_in(outbox)


def test_unknown_email_gets_the_same_answer_and_no_mail(client, outbox):
    assert ask(client, "nobody@dfs-demo.com").status_code == 202
    assert outbox == []


def test_garbage_token_is_rejected(client):
    assert confirm(client, "not-a-real-token-at-all").status_code == 400