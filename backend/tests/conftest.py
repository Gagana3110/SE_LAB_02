import os
import tempfile

# Must be set before the app is imported, so tests never touch a real database.
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth.models import Role  # noqa: E402
from app.auth.service import create_user  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

PASSWORD = "correct-horse-battery"


@pytest.fixture(autouse=True)
def fresh_database():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def make_user(db):
    def make(role: Role, email: str | None = None):
        return create_user(db, email or f"{role.value}@dfs-demo.com", PASSWORD, role)

    return make


@pytest.fixture
def login_as(client, make_user):
    def login(role: Role):
        user = make_user(role)
        response = client.post("/api/auth/login", json={"email": user.email, "password": PASSWORD})
        assert response.status_code == 200
        return user

    return login
