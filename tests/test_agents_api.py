import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.main import app
from storage.db import get_session
from storage.models import Base

VALID_PAYLOAD = {
    "name": "Acme Support",
    "system_prompt": "You are a helpful Acme Telecom support agent.",
    "voice": "sonic-3",
    "model": "gpt-4.1",
}


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_session():
        session = TestSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_get_session
    try:
        # Not used as a context manager: that would run the app's lifespan,
        # which calls init_db() against the real on-disk DB instead of this
        # fixture's temp engine. Tables are already created above.
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_create_and_fetch_agent(client):
    created = client.post("/agents", json=VALID_PAYLOAD)
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == VALID_PAYLOAD["name"]
    assert "id" in body

    fetched = client.get(f"/agents/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == body


def test_get_unknown_agent_is_404(client):
    response = client.get("/agents/999999")
    assert response.status_code == 404


@pytest.mark.parametrize("missing_field", ["name", "system_prompt", "voice", "model"])
def test_create_agent_missing_field_is_422(client, missing_field):
    payload = dict(VALID_PAYLOAD)
    del payload[missing_field]
    response = client.post("/agents", json=payload)
    assert response.status_code == 422


@pytest.mark.parametrize("empty_field", ["name", "system_prompt", "voice", "model"])
def test_create_agent_empty_field_is_422(client, empty_field):
    payload = dict(VALID_PAYLOAD)
    payload[empty_field] = ""
    response = client.post("/agents", json=payload)
    assert response.status_code == 422
