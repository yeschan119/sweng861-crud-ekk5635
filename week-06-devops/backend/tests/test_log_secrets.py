"""No log line carries a token, a cookie, an OAuth code, a configured secret or an email.

Every path that handles one runs through the real app, and every line written at
any level is then searched for each value.

AI use: drafting and test-case enumeration.
"""

from urllib.parse import parse_qs, urlsplit

import pytest

import main
import ratelimit
from config import get_settings
from db import get_db
from models import User
from oidc import GoogleIdentity

CODE = "oauth-code-4f1c9e"
STATE = "oauth-state-8b2d77"
NONCE = "oauth-nonce-c03a51"
VERIFIER = "pkce-verifier-91e6f0"
EMAIL = "student-secret-check@psu.edu"
CALLBACK = f"/auth/callback?code={CODE}&state={STATE}"


@pytest.fixture(autouse=True)
def offline_login(monkeypatch):
    ratelimit._login_window = ratelimit.SlidingWindow()
    monkeypatch.setattr(main, "exchange_code_for_tokens", lambda code, verifier: {"id_token": "x"})
    monkeypatch.setattr(
        main,
        "verify_id_token",
        lambda id_token, nonce: GoogleIdentity(subject="sub-1", email=EMAIL, name="Student"),
    )
    monkeypatch.setattr(main, "upsert_user", lambda db, identity: User(id=7, email=identity.email))
    main.app.dependency_overrides[get_db] = lambda: None
    yield
    main.app.dependency_overrides.clear()


def _set_login_cookies(client):
    client.cookies.clear()
    for name, value in (
        (main.STATE_COOKIE, STATE),
        (main.NONCE_COOKIE, NONCE),
        (main.VERIFIER_COOKIE, VERIFIER),
    ):
        client.cookies.set(name, value, path="/auth")


def _issued_token(response) -> str:
    return parse_qs(urlsplit(response.headers["location"]).fragment)["access_token"][0]


def test_no_secret_reaches_any_log_line(client, json_logs, monkeypatch):
    # A completed login: code, state, the three login cookies, and the token it issues.
    _set_login_cookies(client)
    token = _issued_token(client.get(CALLBACK, follow_redirects=False))

    # Refused logins: with the cookies but a forged state, and with no cookies at all.
    _set_login_cookies(client)
    client.get(f"/auth/callback?code={CODE}&state=forged", follow_redirects=False)
    client.cookies.clear()
    client.get(CALLBACK, follow_redirects=False)

    # The token presented as a bearer credential, and a forged one that is refused.
    client.get("/api/hello", headers={"Authorization": f"Bearer {token}"})
    client.get("/api/hello", headers={"Authorization": f"Bearer {token}tampered"})

    # An unhandled error in the middle of a login, so the 500 path sees all of it.
    def crash(db, identity):
        raise RuntimeError("database went away")

    monkeypatch.setattr(main, "upsert_user", crash)
    _set_login_cookies(client)
    crashed = client.get(CALLBACK, follow_redirects=False)
    client.cookies.clear()

    assert crashed.status_code == 500
    logs = "\n".join(json_logs)
    assert '"event": "request"' in logs  # the search below ran over real output

    settings = get_settings()
    for secret in (
        CODE,
        STATE,
        NONCE,
        VERIFIER,
        token,
        EMAIL,
        settings.google_client_secret,
        settings.session_jwt_secret,
    ):
        assert secret not in logs
