"""Request metrics: counted by route template and status, served at /metrics.

AI use: drafting and test-case enumeration.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from errors import install_error_handlers
from request_logging import RequestLoggingMiddleware


def _requests(method, route, status):
    labels = {"method": method, "route": route, "status": status}
    return REGISTRY.get_sample_value("http_requests_total", labels) or 0.0


def _latency_count(method, route):
    labels = {"method": method, "route": route}
    return REGISTRY.get_sample_value("http_request_duration_seconds_count", labels) or 0.0


def test_metrics_are_served_in_the_prometheus_text_format(client):
    client.get("/health/live")

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "http_requests_total" in response.text
    assert "http_request_duration_seconds_bucket" in response.text


def test_a_request_is_counted_under_its_route_template_not_its_path(client):
    route = "/api/coverages/{coverage_id}"
    before = _requests("GET", route, "401")

    client.get("/api/coverages/101")
    client.get("/api/coverages/202")

    assert _requests("GET", route, "401") == before + 2
    assert _requests("GET", "/api/coverages/101", "401") == 0.0


def test_latency_is_observed_for_every_request(client):
    before = _latency_count("GET", "/health/live")

    client.get("/health/live")

    assert _latency_count("GET", "/health/live") == before + 1


def test_unmatched_paths_share_one_series(client):
    before = _requests("GET", "unmatched", "404")

    client.get("/wp-admin/setup.php")
    client.get("/.env")

    assert _requests("GET", "unmatched", "404") == before + 2


def test_an_unknown_method_cannot_create_a_series(client):
    before = _requests("OTHER", "unmatched", "404")

    client.request("XYZZY", "/anything")

    assert _requests("OTHER", "unmatched", "404") == before + 1
    assert REGISTRY.get_sample_value(
        "http_requests_total", {"method": "XYZZY", "route": "unmatched", "status": "404"}
    ) is None


@pytest.fixture
def failing_api():
    app = FastAPI()
    install_error_handlers(app)
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/metrics-test/boom")
    def boom():
        raise RuntimeError("internal detail")

    return TestClient(app, raise_server_exceptions=False)


def test_an_unhandled_error_is_counted_as_a_500(failing_api):
    before = _requests("GET", "/metrics-test/boom", "500")

    failing_api.get("/metrics-test/boom")

    assert _requests("GET", "/metrics-test/boom", "500") == before + 1
