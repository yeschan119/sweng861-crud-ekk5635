"""One error shape for every failure this API can produce.

Part 3 of the assignment asks for proper error handling on all endpoints. The
useful reading of "proper" is not that each handler writes a careful message —
handlers already did — but that a client sees the same JSON object no matter
which layer refused the request, and that no layer answers with something the
client was never meant to see.

Three families of failure reach a client, and before this module they answered
in three different shapes:

* an ``HTTPException`` a handler raised on purpose — 400, 401, 404, 409, 429;
* an ``HTTPException`` Starlette raised for us — 404 for an unrouted path, 405
  for the wrong verb — whose detail is a plain string;
* a request that never reached a handler because the body failed validation
  (422), which FastAPI answers with a list under ``detail``;
* anything unforeseen, which Starlette answers with the plain-text body
  ``Internal Server Error``.

All four now answer::

    {"error": "<reason phrase>", "message": "<what a caller can act on>"}

with an optional ``details`` array on 422 and an ``incident`` id on 500.

``error`` is derived from the status code rather than written by the raiser.
Handlers used to spell out ``{"error": "Not Found", ...}`` beside a 404, which
is one more place for the two to disagree; deriving it means the code and the
phrase cannot drift apart.
"""

import logging
import uuid
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("sweng861.errors")

# How long a client is told to wait before retrying a failed collection. A
# fixed, modest number: this service has no way to know when SEC will recover,
# and a header that guesses too high turns a blip into an outage for whoever
# believes it.
UPSTREAM_RETRY_AFTER_SECONDS = 60


# Phrases that moved between Python releases. 422 was renamed from
# "Unprocessable Entity" to "Unprocessable Content" in Python 3.13, following
# RFC 9110. Reading the phrase out of the standard library alone would make the
# published error body depend on which interpreter the service happens to run
# on: one string on a laptop, another inside the container image, a third in
# CI. The contract is pinned here so it is a property of the API instead.
PINNED_PHRASES = {422: "Unprocessable Content"}


def reason_phrase(status_code: int) -> str:
    """The RFC 9110 reason phrase for a status code, e.g. 404 -> "Not Found"."""
    if status_code in PINNED_PHRASES:
        return PINNED_PHRASES[status_code]
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        # A code outside the registry should never be raised here, but a
        # KeyError inside an error handler would turn a handled 4xx into an
        # unhandled 500 - the one place that must not fail.
        return "Error"


def error_response(
    status_code: int,
    message: str,
    *,
    headers: dict[str, str] | None = None,
    **extra: object,
) -> JSONResponse:
    """Build the one error body every failure in this service answers with."""
    body: dict[str, object] = {"error": reason_phrase(status_code), "message": message}
    body.update(extra)
    return JSONResponse(body, status_code=status_code, headers=headers)


async def handle_http_exception(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Deliberate refusals: everything a handler raised, plus Starlette's own.

    ``exc.detail`` is the message when a handler wrote one. Starlette fills it
    with the reason phrase for the errors it raises itself, so an unrouted path
    still answers ``{"error": "Not Found", "message": "Not Found"}`` rather than
    a shape of its own.

    ``exc.headers`` is carried through: the 401 gate's ``WWW-Authenticate`` and
    the rate limiter's ``Retry-After`` are part of those responses, and dropping
    them here would quietly break both.
    """
    message = exc.detail if isinstance(exc.detail, str) else reason_phrase(exc.status_code)
    return error_response(exc.status_code, message, headers=exc.headers)


async def handle_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """A malformed request: 422, with which fields were wrong and why.

    Only ``loc`` and ``msg`` are copied out of Pydantic's report. The rest of
    each entry is dropped on purpose:

    * ``input`` echoes the value the client sent. A 422 body ends up in logs,
      in screenshots and in bug reports, and echoing the submitted value puts
      whatever was in that field into all three.
    * ``url`` and ``ctx`` name the validation library and its version. Which
      library validates the body is not a caller's business, and advertising it
      hands an attacker a dependency to look up advisories for.
    """
    details = [
        {"field": ".".join(str(part) for part in error["loc"]), "message": error["msg"]}
        for error in exc.errors()
    ]
    return error_response(
        # The literal, not HTTPStatus.UNPROCESSABLE_CONTENT: that name only
        # exists from Python 3.13, so on an older interpreter this module would
        # fail to import and take the whole service with it. The number is the
        # part of the status that never moved, and PINNED_PHRASES is keyed by it
        # for the same reason.
        422,
        "Request validation failed",
        details=details,
    )


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """A bug: 500, saying nothing about what broke.

    The default body for an unhandled exception is the plain-text string
    ``Internal Server Error``, which is neither JSON nor consistent with every
    other error this API returns. Answering with the standard shape is half the
    fix; the other half is that the shape must stay empty of detail. An
    exception message is written for a developer and routinely contains a
    table name, a file path, or a fragment of a query.

    So the client gets a random ``incident`` id and nothing else, and the log
    line carries the same id next to the traceback. That is what makes "the API
    returned incident 3f2a..." a searchable report rather than a guess, without
    the response itself explaining how the service is built.

    Starlette re-raises after this handler runs, so the ASGI server prints the
    traceback a second time. Ours is the copy that carries the id.
    """
    incident = uuid.uuid4().hex[:12]
    logger.exception(
        "unhandled error incident=%s %s %s", incident, request.method, request.url.path
    )
    return error_response(
        HTTPStatus.INTERNAL_SERVER_ERROR,
        "An unexpected error occurred",
        incident=incident,
    )


async def handle_upstream_error(request: Request, exc: Exception) -> JSONResponse:
    """A third-party API failed. That is not this service failing.

    Without this handler an EdgarError would reach handle_unexpected_error and
    answer 500, which says "we have a bug" about an afternoon when SEC was
    down. Issue #6 asked that an outage upstream not take these endpoints down
    with it; this is where that promise is kept, and it is registered here
    rather than caught in a route so that an endpoint added later inherits it.

    The two answers differ because the two failures do. EdgarUnavailable means
    the request never got through - a timeout, or a 5xx that survived the
    retries - so the caller is told to try again and given a Retry-After.
    Anything else means the response was unusable, and repeating it would
    produce the same unusable response, so there is nothing to retry.

    The body names no provider, no field and no library. A 502 travels into
    logs, screenshots and bug reports exactly as a 422 does; which upstream
    this service reads, and which library parses it, is not a caller's business
    and is a dependency an attacker can look up advisories for. The detail goes
    to the log beside an incident id.
    """
    from edgar import EdgarUnavailable

    incident = uuid.uuid4().hex[:12]
    logger.warning(
        "upstream failure incident=%s %s %s: %s",
        incident, request.method, request.url.path, exc,
    )

    if isinstance(exc, EdgarUnavailable):
        return error_response(
            HTTPStatus.SERVICE_UNAVAILABLE,
            "The external data provider is temporarily unreachable. Try again shortly.",
            headers={"Retry-After": str(UPSTREAM_RETRY_AFTER_SECONDS)},
        )

    return error_response(
        HTTPStatus.BAD_GATEWAY,
        "The external data provider returned a response this service could not use.",
    )


def install_error_handlers(app: FastAPI) -> None:
    """Register the three handlers on the application.

    Registered in one function rather than as decorators next to the routes so
    that the error contract lives in a single file. An endpoint added later
    inherits it by existing - there is nothing for the author of that endpoint
    to remember to do.

    Order matters only in that the Exception handler is the fallback: Starlette
    picks the most specific registered class for a raised exception, so
    EdgarError is answered by its own handler rather than by that one.
    """
    # Imported here rather than at module scope: this module is the error
    # contract for the whole service, and it should not fail to import because
    # one feature's client is missing.
    from edgar import EdgarError

    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(EdgarError, handle_upstream_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
