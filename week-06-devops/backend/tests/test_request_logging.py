"""The request middleware: one JSON line per request, traced by a request ID.

AI use: drafting and test-case enumeration.
"""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from errors import install_error_handlers
from request_logging import REQUEST_ID_HEADER, RequestLoggingMiddleware


@pytest.fixture
def api():
    """A small app wired the way main.py wires it, with one route that fails."""
    app = FastAPI()
    install_error_handlers(app)
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/ok")
    def ok():
        import logging

        logging.getLogger("sweng861.test").info("inside the handler")
        return {"ok": True}

    @app.get("/boom")
    def boom():
        raise RuntimeError("internal detail")

    return TestClient(app, raise_server_exceptions=False)


def _entries(lines, **match):
    entries = [json.loads(line) for line in lines]
    return [e for e in entries if all(e.get(k) == v for k, v in match.items())]


def test_an_incoming_request_id_is_kept_and_returned(api, json_logs):
    response = api.get("/ok", headers={REQUEST_ID_HEADER: "trace-1"})

    assert response.headers[REQUEST_ID_HEADER] == "trace-1"
    [line] = _entries(json_logs, event="request")
    assert line["request_id"] == "trace-1"


def test_a_request_without_an_id_is_given_one(api, json_logs):
    response = api.get("/ok")

    generated = response.headers[REQUEST_ID_HEADER]
    assert len(generated) == 32
    assert _entries(json_logs, event="request")[0]["request_id"] == generated


@pytest.mark.parametrize("unsafe", ["a b", 'x"y', "x" * 65, "line\\nbreak"])
def test_an_unsafe_incoming_id_is_replaced(api, unsafe):
    response = api.get("/ok", headers={REQUEST_ID_HEADER: unsafe})

    assert response.headers[REQUEST_ID_HEADER] != unsafe


def test_every_line_written_while_serving_carries_the_same_id(api, json_logs):
    api.get("/ok", headers={REQUEST_ID_HEADER: "trace-2"})

    handler_line = _entries(json_logs, message="inside the handler")[0]
    request_line = _entries(json_logs, event="request")[0]
    assert handler_line["request_id"] == request_line["request_id"] == "trace-2"


def test_the_request_line_has_method_path_status_and_duration(api, json_logs):
    api.get("/ok?code=oauth-code-value&state=xyz")

    [line] = _entries(json_logs, event="request")
    assert line["method"] == "GET"
    assert line["path"] == "/ok"
    assert line["status"] == 200
    assert line["duration_ms"] >= 0
    assert "oauth-code-value" not in json.dumps(line)


def test_an_unhandled_error_keeps_the_id_on_the_incident_and_the_response(api, json_logs):
    response = api.get("/boom", headers={REQUEST_ID_HEADER: "trace-500"})

    assert response.status_code == 500
    assert response.headers[REQUEST_ID_HEADER] == "trace-500"
    incident = response.json()["incident"]
    [error_line] = _entries(json_logs, level="ERROR")
    assert incident in error_line["message"]
    assert error_line["event"] == "unexpected_error"
    assert error_line["incident"] == incident
    assert error_line["request_id"] == "trace-500"
    assert _entries(json_logs, event="request")[0]["status"] == 500


def test_the_real_app_returns_a_request_id(client):
    assert REQUEST_ID_HEADER in client.get("/health/live").headers
