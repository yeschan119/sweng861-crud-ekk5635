"""Bonus: rate limiting on the login endpoints and logging of rejected tokens."""

import logging

import pytest

import main
import ratelimit
from oidc import ProviderMetadata
from ratelimit import FAILED_AUTH_LIMIT, LOGIN_LIMIT

# Stands in for the discovery document so the suite never calls Google. The
# rate limiter is what is under test; where the redirect points is not.
FAKE_PROVIDER = ProviderMetadata(
    issuer="https://accounts.google.com",
    authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
    token_endpoint="https://oauth2.googleapis.com/token",
    jwks_uri="https://www.googleapis.com/oauth2/v3/certs",
)


@pytest.fixture(autouse=True)
def clean_windows(monkeypatch):
    """Each test starts with empty counters and an offline provider.

    The windows are module-level state, so without this a test would inherit
    whatever requests an earlier test made.
    """
    ratelimit._login_window = ratelimit.SlidingWindow()
    ratelimit._failed_auth_window = ratelimit.SlidingWindow()
    monkeypatch.setattr(main, "get_provider_metadata", lambda: FAKE_PROVIDER)
    yield


def test_login_is_allowed_up_to_the_limit(client):
    for attempt in range(LOGIN_LIMIT.max_events):
        response = client.get("/auth/login", follow_redirects=False)
        assert response.status_code == 302, f"attempt {attempt + 1} should pass"


def test_login_is_throttled_past_the_limit(client):
    for _ in range(LOGIN_LIMIT.max_events):
        client.get("/auth/login", follow_redirects=False)

    response = client.get("/auth/login", follow_redirects=False)

    assert response.status_code == 429
    assert response.json() == {
        "error": "Too Many Requests",
        "message": "Slow down and try again shortly",
    }
    # RFC 6585: tell the caller when to come back.
    assert int(response.headers["retry-after"]) >= 1


def test_one_address_does_not_consume_another_addresss_allowance():
    """Counting is per key, so a noisy client cannot lock everyone else out."""
    window = ratelimit.SlidingWindow()

    for _ in range(LOGIN_LIMIT.max_events):
        window.record("10.0.0.1", LOGIN_LIMIT)

    allowed_first, _, _ = window.record("10.0.0.1", LOGIN_LIMIT)
    allowed_second, _, _ = window.record("10.0.0.2", LOGIN_LIMIT)

    assert allowed_first is False
    assert allowed_second is True


def test_login_throttling_does_not_spend_the_failed_auth_allowance(client):
    """Separate windows: a login burst must not mask token abuse, or vice versa."""
    for _ in range(LOGIN_LIMIT.max_events + 5):
        client.get("/auth/login", follow_redirects=False)

    allowed, count, _ = ratelimit._failed_auth_window.record("testclient", FAILED_AUTH_LIMIT)

    assert allowed is True
    assert count == 1


def test_repeated_rejected_tokens_are_summarized_in_the_log(client, caplog):
    """The 'log suspicious activity' half of the bonus."""
    with caplog.at_level(logging.WARNING, logger="sweng861.security"):
        for _ in range(FAILED_AUTH_LIMIT.max_events + 1):
            response = client.get(
                "/api/hello", headers={"Authorization": "Bearer forged"}
            )
            assert response.status_code == 401

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings, "a burst of rejected tokens should raise a warning"
    assert "suspicious activity" in warnings[0].getMessage()


def test_a_single_rejected_token_does_not_raise_a_warning(client, caplog):
    """One 401 is noise; the log should not cry wolf over it."""
    with caplog.at_level(logging.WARNING, logger="sweng861.security"):
        client.get("/api/hello", headers={"Authorization": "Bearer forged"})

    assert [r for r in caplog.records if r.levelno == logging.WARNING] == []
