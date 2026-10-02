"""Prometheus metrics for the API: request counts and latency by route, plus domain counters."""

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.requests import Request
from starlette.responses import Response

# Labels come from a fixed set so a caller cannot mint a new time series per request.
UNMATCHED_ROUTE = "unmatched"
OTHER_METHOD = "OTHER"
KNOWN_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})

REQUESTS = Counter(
    "http_requests_total",
    "HTTP requests by method, route template and status code.",
    ["method", "route", "status"],
)
# 0.5 s is a bucket edge so the p95 <= 500 ms SLO reads exactly, not interpolated.
LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency by method and route template.",
    ["method", "route"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)


def route_of(request: Request) -> str:
    """The matched route's template (/api/coverages/{coverage_id}), never the raw path."""
    route = request.scope.get("route")
    return getattr(route, "path", UNMATCHED_ROUTE)


def method_of(request: Request) -> str:
    return request.method if request.method in KNOWN_METHODS else OTHER_METHOD


def observe_request(request: Request, status: int, seconds: float) -> None:
    method, route = method_of(request), route_of(request)
    REQUESTS.labels(method, route, str(status)).inc()
    LATENCY.labels(method, route).observe(seconds)


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# --- Domain counters --------------------------------------------------------

COVERAGES_CREATED = Counter("coverages_created_total", "Coverages created through the API.")

# The login SLI counts only failures the service caused; these are the caller's own.
CLIENT_LOGIN_FAILURES = frozenset({"provider_error", "missing_cookies", "state_mismatch"})
LOGIN_OUTCOMES = ("succeeded", "client_error", "service_error")
LOGINS = Counter("logins_total", "Completed /auth/callback attempts by outcome.", ["outcome"])
# Every outcome exists at 0 from start-up, so a ratio has a denominator before the first failure.
for _outcome in LOGIN_OUTCOMES:
    LOGINS.labels(_outcome)


def record_login_success() -> None:
    LOGINS.labels("succeeded").inc()


def record_login_failure(reason: str) -> None:
    outcome = "client_error" if reason in CLIENT_LOGIN_FAILURES else "service_error"
    LOGINS.labels(outcome).inc()
