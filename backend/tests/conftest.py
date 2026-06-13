import os

# Test-Umgebung VOR allen App-Importen setzen
os.environ["KMUOS_DATABASE_URL"] = "sqlite:///./test_kmuos.db"
os.environ["KMUOS_SECRET_KEY"] = "test-secret-mit-mindestens-32-zeichen-laenge"
os.environ["KMUOS_ALLOW_SIGNUP"] = "true"   # für Mandanten-Isolations-Tests
os.environ["KMUOS_SCHEDULER_ENABLED"] = "false"
os.environ.pop("ANTHROPIC_API_KEY", None)  # Tests laufen immer ohne echte KI

import pytest
from fastapi.testclient import TestClient

from backend.app.core import events
from backend.app.core.database import Base, engine
from backend.app.main import app

ADMIN = {
    "company_name": "Testfirma GmbH",
    "industry": "IT",
    "admin_name": "Test Admin",
    "admin_email": "admin@testfirma.de",
    "admin_password": "geheim123",
}


def login(client: TestClient, email: str, password: str, tenant_slug: str | None = None) -> str:
    payload = {"email": email, "password": password}
    if tenant_slug:
        payload["tenant_slug"] = tenant_slug
    response = client.post("/api/auth/login", json=payload)
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture()
def anon_client():
    """Client ohne Setup/Token — für Setup- und Auth-Tests."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    events.reset()
    with TestClient(app) as test_client:
        yield test_client
    events.reset()


@pytest.fixture()
def client(anon_client):
    """Client mit eingerichtetem Mandanten und Admin-Token."""
    response = anon_client.post("/api/setup", json=ADMIN)
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    anon_client.headers["Authorization"] = f"Bearer {token}"
    yield anon_client
