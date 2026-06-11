import os

# Test-Datenbank VOR allen App-Importen setzen
os.environ["KMUOS_DATABASE_URL"] = "sqlite:///./test_kmuos.db"

import pytest
from fastapi.testclient import TestClient

from backend.app.core import events
from backend.app.core.database import Base, engine
from backend.app.main import app


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    events.reset()
    with TestClient(app) as test_client:  # Context-Manager triggert lifespan
        yield test_client
    events.reset()
