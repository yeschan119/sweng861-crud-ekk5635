"""How /auth/callback hands the outcome of a login to the single-page app.

Google, the token exchange and the users table are replaced: what is under test
is where the browser is sent and what it carries, not OIDC itself. The token a
successful login produces is then presented to the protected endpoint, so the
test proves it is a working credential rather than a string in the right place.
"""

from urllib.parse import parse_qs, urlsplit

import pytest

import main
import ratelimit
from config import get_settings
from db import get_db
from models import User
from oidc import GoogleIdentity, OidcError

COOKIES = {
    main.STATE_COOKIE: "expected-state",
    main.NONCE_COOKIE: "expected-nonce",
    main.VERIFIER_COOKIE: "expected-verifier",
}


@pytest.fixture(autouse=True)
def offline_login(monkeypatch):
    """No request leaves the test, and the login allowance starts empty."""
    ratelimit._login_window = ratelimit.SlidingWindow()
    monkeypatch.setattr(
        main, "exchange_code_for_tokens", lambda code, verifier: {"id_token": "fake"}
    )
    monkeypatch.setattr(
        main,
        "verify_id_token",
        lambda id_token, nonce: GoogleIdentity(
            subject="google-subject", email="student@psu.edu", name="Student"
        ),
    )
    # Not persisted: issue_session_token reads only the id and the email.
    monkeypatch.setattr(
        main, "upsert_user", lambda db, identity: User(id=7, email=identity.email)
    )
    main.app.dependency_overrides[get_db] = lambda: None
    yield
    main.app.dependency_overrides.clear()


def _callback(client, query: str, cookies: dict[str, str] = COOKIES):
    # Cookies go on the client, not the request: that is how a browser holds
    # them, and TestClient deprecates per-request cookies.
    client.cookies.clear()
    for name, value in cookies.items():
        client.cookies.set(name, value, path="/auth")
    return client.get(f"/auth/callback?{query}", follow_redirects=False)


def _fragment(response) -> dict[str, list[str]]:
    """The redirect target's fragment, parsed, after checking where it points."""
    location = urlsplit(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}" == get_settings().frontend_url
    assert location.path == main.LOGIN_PAGE_PATH
    return parse_qs(location.fragment)


def test_a_completed_login_sends_the_token_to_the_frontend(client):
    response = _callback(client, "code=abc&state=expected-state")

    assert response.status_code == 302
    token = _fragment(response)["access_token"][0]

    client.cookies.clear()
    hello = client.get("/api/hello", headers={"Authorization": f"Bearer {token}"})
    assert hello.status_code == 200


def test_a_completed_login_spends_the_login_cookies(client):
    response = _callback(client, "code=abc&state=expected-state")

    cleared = response.headers.get_list("set-cookie")
    for name in COOKIES:
        assert any(h.startswith(f"{name}=") and "Max-Age=0" in h for h in cleared)


def test_the_token_is_never_put_in_the_query_string(client):
    """The query string reaches servers and logs; the fragment does not."""
    response = _callback(client, "code=abc&state=expected-state")

    assert urlsplit(response.headers["location"]).query == ""


@pytest.mark.parametrize(
    ("query", "cookies"),
    [
        ("error=access_denied&state=expected-state", COOKIES),
        ("state=expected-state", COOKIES),
        ("code=abc", COOKIES),
        ("code=abc&state=expected-state", {}),
        ("code=abc&state=forged-state", COOKIES),
    ],
    ids=["consent-declined", "no-code", "no-state", "no-cookies", "state-mismatch"],
)
def test_a_refused_login_sends_one_generic_reason(client, query, cookies):
    response = _callback(client, query, cookies)

    assert response.status_code == 302
    assert _fragment(response) == {"error": [main.LOGIN_FAILED]}


def test_a_token_google_would_not_vouch_for_is_refused_the_same_way(
    client, monkeypatch
):
    def reject(id_token, nonce):
        raise OidcError("signature did not verify")

    monkeypatch.setattr(main, "verify_id_token", reject)

    response = _callback(client, "code=abc&state=expected-state")

    assert response.status_code == 302
    assert _fragment(response) == {"error": [main.LOGIN_FAILED]}


# ---------------------------------------------------------------------------
# What the server log records about each outcome (the client sees none of it)
# ---------------------------------------------------------------------------


def _auth_events(lines):
    import json

    return [e for e in map(json.loads, lines) if e.get("logger") == "sweng861.auth"]


def test_a_completed_login_is_logged_by_user_id_not_email(client, json_logs):
    _callback(client, "code=abc&state=expected-state")

    [event] = _auth_events(json_logs)
    assert event["event"] == "login_succeeded"
    assert event["user_id"] == 7
    assert "student@psu.edu" not in "\n".join(json_logs)


@pytest.mark.parametrize(
    ("query", "cookies", "reason"),
    [
        ("error=access_denied&state=expected-state", COOKIES, "provider_error"),
        ("code=abc&state=expected-state", {}, "missing_cookies"),
        ("code=abc&state=forged-state", COOKIES, "state_mismatch"),
    ],
    ids=["consent-declined", "no-cookies", "state-mismatch"],
)
def test_a_refused_login_logs_which_check_refused_it(
    client, json_logs, query, cookies, reason
):
    _callback(client, query, cookies)

    [event] = _auth_events(json_logs)
    assert event["event"] == "login_failed"
    assert event["level"] == "WARNING"
    assert event["reason"] == reason


def test_an_oidc_failure_logs_the_underlying_error_class(client, json_logs, monkeypatch):
    import jwt

    def expired(id_token, nonce):
        try:
            raise jwt.ExpiredSignatureError("Signature has expired")
        except jwt.PyJWTError as exc:
            raise OidcError(f"id_token verification failed: {exc}") from exc

    monkeypatch.setattr(main, "verify_id_token", expired)

    _callback(client, "code=abc&state=expected-state")

    [event] = _auth_events(json_logs)
    assert event["reason"] == "oidc_error:ExpiredSignatureError"


def test_an_oidc_failure_without_a_cause_logs_its_fixed_message(
    client, json_logs, monkeypatch
):
    def mismatch(id_token, nonce):
        raise OidcError("id_token nonce did not match the login attempt")

    monkeypatch.setattr(main, "verify_id_token", mismatch)

    _callback(client, "code=abc&state=expected-state")

    [event] = _auth_events(json_logs)
    assert event["reason"] == "oidc_error:id_token nonce did not match the login attempt"
