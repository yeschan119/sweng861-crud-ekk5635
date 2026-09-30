"""Health probes with the database up and down.

The down case is a real connection failure to a closed port, not a mock, so it
exercises the same exception path a stopped database container produces.
"""

import pytest
from sqlalchemy import Engine, create_engine

from conftest import needs_db

# Port 1 is never listened on locally; the timeout keeps the test bounded where packets are dropped.
UNREACHABLE_DATABASE_URL = "postgresql+psycopg://nobody:nothing@127.0.0.1:1/none?connect_timeout=1"


def client_with_probe_engine(engine: Engine):
    """A client whose health checks connect through the given engine."""
    from fastapi.testclient import TestClient

    from db import get_probe_engine
    from main import app

    app.dependency_overrides[get_probe_engine] = lambda: engine
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def api_without_database():
    engine = create_engine(UNREACHABLE_DATABASE_URL)
    yield from client_with_probe_engine(engine)
    engine.dispose()


@pytest.fixture
def api_with_database(db_engine):
    yield from client_with_probe_engine(db_engine)


@needs_db
@pytest.mark.parametrize("path", ["/health", "/health/ready"])
def test_database_up_answers_200_up(api_with_database, path):
    response = api_with_database.get(path)

    assert response.status_code == 200
    assert response.json() == {"status": "UP", "db": "UP"}


@pytest.mark.parametrize("path", ["/health", "/health/ready"])
def test_database_down_answers_503_down(api_without_database, path):
    response = api_without_database.get(path)

    assert response.status_code == 503
    assert response.json() == {"status": "DOWN", "db": "DOWN"}


def test_liveness_ignores_the_database(api_without_database):
    response = api_without_database.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "UP"}


def test_failed_check_logs_the_error_type_only(api_without_database, caplog):
    with caplog.at_level("WARNING", logger="sweng861.health"):
        api_without_database.get("/health")

    [record] = caplog.records
    assert record.getMessage() == "database health check failed: OperationalError"
    # The connection string's user and host must not reach the log.
    assert "nobody" not in caplog.text
    assert "127.0.0.1" not in caplog.text
