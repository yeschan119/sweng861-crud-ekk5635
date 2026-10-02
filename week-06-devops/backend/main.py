"""FastAPI application for Week 4 — the Week 3 API, consumed by the Vue single-page app.

Carried over from week-02-auth unchanged: the Google OIDC login flow, the
session token, the requireAuth gate, and rate limiting. Week 3 adds the
coverages resource, the SEC EDGAR client, and global error handling on top.
"""

import base64
import hashlib
import logging
import secrets
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from admin import router as admin_router
from config import get_settings
from coverages import router as coverages_router
from financials import router as financials_router
from db import get_db
from errors import install_error_handlers
from health import router as health_router
from logging_setup import configure_logging
from request_logging import RequestLoggingMiddleware
from ratelimit import limit_login
from oidc import (
    OidcError,
    exchange_code_for_tokens,
    get_provider_metadata,
    verify_id_token,
)
from security import AuthenticatedUser, require_auth
from tokens import issue_session_token
from users import upsert_user

# Short-lived cookies that carry the login attempt from the redirect to the
# callback. All three are per-attempt random values; none is a secret the user
# needs, so all three are HttpOnly.
STATE_COOKIE = "oauth_state"      # CSRF: ties the callback to this browser
NONCE_COOKIE = "oauth_nonce"      # replay: ties the id_token to this attempt
VERIFIER_COOKIE = "oauth_verifier"  # PKCE: proves who redeems the code started it

# The user has ten minutes to finish consenting at Google.
STATE_TTL_SECONDS = 600

# openid gets an id_token at all; email and profile are what this app stores.
# Nothing more is requested - an authorization the app does not need is an
# authorization it cannot misuse.
SCOPES = "openid email profile"

# The single-page app's route that finishes a login. The callback ends every
# attempt there, successful or not, because a browser that arrives at the API
# by redirect has no page to show a JSON body in.
LOGIN_PAGE_PATH = "/login"

# The only reason the frontend is ever given. See callback() for why every
# failure shares it.
LOGIN_FAILED = "login_failed"

auth_logger = logging.getLogger("sweng861.auth")


# Before the app exists, so every record from here on is a JSON line.
configure_logging()

# No startup hook creates the schema: `alembic upgrade head` owns it, and an
# application that alters tables as it boots cannot be deployed twice safely.
app = FastAPI(
    title="SWENG 861 Week 4 — Backend API",
    version="0.3.0",
)

app.include_router(health_router)
app.include_router(coverages_router)
app.include_router(financials_router)
app.include_router(admin_router)

# Every failure this service can answer with - a refusal a handler raised, a
# route Starlette could not match, a body that failed validation, or a bug -
# leaves through errors.py in one shape. See that module for why.
install_error_handlers(app)
app.add_middleware(RequestLoggingMiddleware)


@app.get("/auth/login", dependencies=[Depends(limit_login)])
def login() -> RedirectResponse:
    """Leg 1 of the three-legged flow: send the user to Google to authenticate.

    The state parameter is the CSRF defense. It is a random value that goes out
    in the redirect and is simultaneously stored in a cookie on this site. When
    Google sends the user back, /auth/callback only accepts the request if the
    state in the query string matches the one in the cookie. An attacker can
    make a victim's browser hit the callback URL with an authorization code of
    the attacker's own - which would log the victim into the attacker's
    account - but the attacker cannot write a cookie on this origin, so the
    forged request has nothing to match and is rejected.

    Two further values ride along. The nonce is echoed by Google inside the
    id_token, so the callback can tell this attempt's token from an older one
    replayed at it. PKCE sends only the SHA-256 of a random verifier now and
    the verifier itself at redemption, so an authorization code that leaks out
    of the browser cannot be spent by whoever picked it up.

    All three cookies are HttpOnly (script cannot read them), SameSite=Lax
    (sent on the top-level redirect back from Google, but not on cross-site
    subrequests), scoped to /auth (never attached to API calls), and Secure
    whenever the redirect URI is https - http is only ever used for localhost.
    """
    settings = get_settings()
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)

    # S256 challenge: base64url of the SHA-256 digest, no padding, per RFC 7636.
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )

    query = urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": SCOPES,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    authorization_url = f"{get_provider_metadata().authorization_endpoint}?{query}"

    response = RedirectResponse(authorization_url, status_code=302)
    for name, value in (
        (STATE_COOKIE, state),
        (NONCE_COOKIE, nonce),
        (VERIFIER_COOKIE, code_verifier),
    ):
        response.set_cookie(
            name,
            value,
            max_age=STATE_TTL_SECONDS,
            httponly=True,
            samesite="lax",
            secure=settings.google_redirect_uri.startswith("https://"),
            path="/auth",
        )
    return response


def _redirect_to_login_page(**fragment: str) -> RedirectResponse:
    """Send the browser back to the frontend, carrying the outcome in the fragment.

    The fragment rather than the query string: a browser never sends the part
    after "#" to any server, so the session token does not land in the
    frontend host's access log, and it is not in the Referer of any request the
    page goes on to make. The page reads it and clears it from the address bar.
    """
    url = f"{get_settings().frontend_url}{LOGIN_PAGE_PATH}#{urlencode(fragment)}"
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)


def _login_failed(reason: str) -> RedirectResponse:
    """The one answer the client gets; the reason stays in the server log."""
    auth_logger.warning("login failed", extra={"event": "login_failed", "reason": reason})
    return _redirect_to_login_page(error=LOGIN_FAILED)


@app.get("/auth/callback", dependencies=[Depends(limit_login)])
def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Leg 3: Google returns the user here with an authorization code.

    Order matters. The cheap, local checks run before anything is sent to
    Google, so a forged callback is refused without this server making a
    request on its behalf:

    1. did Google report an error, or is the code missing;
    2. does the state in the query match the state in this browser's cookie;
    3. exchange the code, presenting the PKCE verifier;
    4. verify the id_token's signature, issuer, audience, expiry and nonce;
    5. create or update the local user;
    6. issue this application's own session token.

    Both outcomes redirect to the frontend's login page: the token on success,
    and on failure one reason shared by every check. Distinguishing "bad state"
    from "expired code" from "unknown signing key" would let a caller map the
    defenses; the detail goes to the server log instead.
    """
    # The user declined consent, or Google rejected the request.
    if error or not code or not state:
        return _login_failed("provider_error")

    cookie_state = request.cookies.get(STATE_COOKIE)
    nonce = request.cookies.get(NONCE_COOKIE)
    code_verifier = request.cookies.get(VERIFIER_COOKIE)
    if not cookie_state or not nonce or not code_verifier:
        # No cookies means this callback did not start at /auth/login in this
        # browser - or it sat past the ten-minute window.
        return _login_failed("missing_cookies")

    if not secrets.compare_digest(state, cookie_state):
        return _login_failed("state_mismatch")

    try:
        google_tokens = exchange_code_for_tokens(code, code_verifier)
        identity = verify_id_token(google_tokens["id_token"], nonce)
    except OidcError as exc:
        # The underlying error's class (expired, bad signature, HTTP 400), never its text.
        cause = type(exc.__cause__).__name__ if exc.__cause__ else str(exc)
        return _login_failed(f"oidc_error:{cause}")

    user = upsert_user(db, identity)
    auth_logger.info("login succeeded", extra={"event": "login_succeeded", "user_id": user.id})

    # Only the token. Its type is always bearer, and the frontend learns that
    # it expired from the 401 the API answers with, so neither travels.
    response = _redirect_to_login_page(access_token=issue_session_token(user))

    # The login transaction is over; these have no further use, and a spent
    # verifier or nonce sitting in the browser is only exposure.
    for name in (STATE_COOKIE, NONCE_COOKIE, VERIFIER_COOKIE):
        response.delete_cookie(name, path="/auth")

    return response


@app.get("/api/hello")
def hello(user: AuthenticatedUser = Depends(require_auth)) -> dict[str, str]:
    """The protected endpoint. Without a valid token this is a 401.

    Three OWASP API risks shape these six lines.

    Broken Object Level Authorization: the identity comes from the verified
    token and from nowhere else. There is no user id in the path or the query
    string, so there is no identifier for a caller to change in order to be
    answered as somebody else. When Week 3 adds records, the same rule becomes
    a where-clause on owner_id taken from this same token.

    Excessive Data Exposure: the response is one sentence. Returning the user
    object, or the token's claims, would leak fields the client never asked for
    and would grow to leak whatever is added to the model later.

    Security Misconfiguration: nothing here can produce a stack trace for the
    client. The failure paths are the gate's single 401, and the exception
    handler emits no internal detail.
    """
    return {"message": f"Hello, {user.email or 'user'}!"}
