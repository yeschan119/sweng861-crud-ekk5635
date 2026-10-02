"""One JSON line per request, tagged with a request ID the caller can see."""

import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from errors import handle_unexpected_error
from logging_setup import request_id_var

logger = logging.getLogger("sweng861.request")

REQUEST_ID_HEADER = "X-Request-ID"
# The incoming value is written into log lines, so anything that could break a line is refused.
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9-]{1,64}")


def _request_id_from(request: Request) -> str:
    incoming = request.headers.get(REQUEST_ID_HEADER, "")
    if _VALID_REQUEST_ID.fullmatch(incoming):
        return incoming
    return uuid.uuid4().hex


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = _request_id_from(request)
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception as exc:
                # Answered here, not by Starlette's outer handler, so the incident log keeps the ID.
                response = await handle_unexpected_error(request, exc)
            response.headers[REQUEST_ID_HEADER] = request_id
            logger.info(
                "%s %s %s",
                request.method,
                request.url.path,
                response.status_code,
                extra={
                    "event": "request",
                    "method": request.method,
                    # The path only: a query string can carry an OAuth code or state.
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                },
            )
            return response
        finally:
            request_id_var.reset(token)
