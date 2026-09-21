"""Unit tests for oidc.py, with no database and no network.

The callback tests in test_auth_callback.py replace this whole module with
lambdas, so until now not one line of oidc.py ran under test. These tests fill
that hole: Google's two HTTP calls are replaced by fakes, but the verification
itself is real. Tokens are signed here with a freshly generated RSA key and
handed to the actual jwt.decode, so "a token signed by someone else is
refused" is demonstrated rather than asserted about a mock.

Each test is arranged, acted on and asserted in that order, and each one names
the single rule it pins down.
"""

import time
from types import SimpleNamespace

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

import oidc
from config import get_settings
from oidc import (
    OidcError,
    exchange_code_for_tokens,
    get_provider_metadata,
    verify_id_token,
)

ISSUER = "https://accounts.google.com"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
JWKS_URI = "https://www.googleapis.com/oauth2/v3/certs"

DISCOVERY_DOCUMENT = {
    "issuer": ISSUER,
    "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
    "token_endpoint": TOKEN_ENDPOINT,
    "jwks_uri": JWKS_URI,
    # Google publishes some thirty keys here. Keeping one the module ignores
    # proves it reads the four it names rather than the whole document.
    "revocation_endpoint": "https://oauth2.googleapis.com/revoke",
}

EXPECTED_NONCE = "nonce-from-this-login-attempt"


class FakeResponse:
    """The three pieces of httpx.Response that oidc.py touches."""

    def __init__(self, payload: dict, error: Exception | None = None):
        self._payload = payload
        self._error = error

    def raise_for_status(self) -> None:
        if self._error is not None:
            raise self._error

    def json(self) -> dict:
        return self._payload


@pytest.fixture(autouse=True)
def clear_process_caches():
    """Undo the lru_cache on the two fetchers around every test.

    Both are cached for the life of the process, so without this one test's
    fake discovery document would be served to every test after it.
    """
    get_provider_metadata.cache_clear()
    oidc._jwks_client.cache_clear()
    yield
    get_provider_metadata.cache_clear()
    oidc._jwks_client.cache_clear()


@pytest.fixture
def discovery(monkeypatch) -> list[str]:
    """Serve the discovery document offline, recording every fetch."""
    fetched: list[str] = []

    def fake_get(url, timeout=None):
        fetched.append(url)
        return FakeResponse(DISCOVERY_DOCUMENT)

    monkeypatch.setattr(oidc.httpx, "get", fake_get)
    return fetched


@pytest.fixture(scope="session")
def google_key() -> rsa.RSAPrivateKey:
    """The key standing in for Google's signing key."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def impostor_key() -> rsa.RSAPrivateKey:
    """A valid RSA key that Google never published."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def google_signs(monkeypatch, google_key):
    """Point the verifier at the public half of google_key.

    Only the key lookup is faked. jwt.decode still checks the signature, the
    issuer, the audience and the expiry for real.
    """
    public_key = google_key.public_key()
    monkeypatch.setattr(
        oidc,
        "_jwks_client",
        lambda: SimpleNamespace(
            get_signing_key_from_jwt=lambda token: SimpleNamespace(key=public_key)
        ),
    )


def make_id_token(private_key, **overrides) -> str:
    """An id_token shaped like Google's, signed with the given key."""
    issued_at = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": get_settings().google_client_id,
        "sub": "google-subject-1234567890",
        "iat": issued_at,
        "exp": issued_at + 3600,
        "nonce": EXPECTED_NONCE,
        "email": "student@psu.edu",
        "email_verified": True,
        "name": "Test Student",
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256")


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def test_discovery_reads_the_four_endpoints_the_application_uses(discovery):
    metadata = get_provider_metadata()

    assert discovery == [oidc.GOOGLE_DISCOVERY_URL]
    assert metadata.issuer == ISSUER
    assert metadata.token_endpoint == TOKEN_ENDPOINT
    assert metadata.jwks_uri == JWKS_URI
    assert metadata.authorization_endpoint.startswith("https://accounts.google.com/")


def test_discovery_is_fetched_once_per_process(discovery):
    first = get_provider_metadata()
    second = get_provider_metadata()

    # One fetch, and the same frozen object both times: a login must not pay
    # for a round trip that returns a document which never changes.
    assert len(discovery) == 1
    assert first is second


def test_a_failed_discovery_fetch_is_not_turned_into_an_oidc_error(monkeypatch):
    """Documents a gap rather than an intention.

    exchange_code_for_tokens and verify_id_token both wrap their failures in
    OidcError, which /auth/callback catches. Discovery does not, so a Google
    outage here escapes the callback's except clause as a 500 instead of the
    generic login-failed redirect. Recorded in the Week 5 report.
    """
    outage = httpx.HTTPStatusError(
        "503 Service Unavailable", request=None, response=None
    )
    monkeypatch.setattr(
        oidc.httpx, "get", lambda url, timeout=None: FakeResponse({}, error=outage)
    )

    with pytest.raises(httpx.HTTPStatusError):
        get_provider_metadata()


def test_the_key_client_is_built_from_the_discovered_jwks_uri(discovery):
    client = oidc._jwks_client()

    assert client.uri == JWKS_URI


# ---------------------------------------------------------------------------
# Leg 2: the back-channel token exchange
# ---------------------------------------------------------------------------


def test_the_token_request_carries_the_secret_the_code_and_the_verifier(
    discovery, monkeypatch
):
    sent = {}

    def fake_post(url, data=None, timeout=None):
        sent["url"] = url
        sent["data"] = data
        return FakeResponse({"id_token": "signed.by.google", "access_token": "at"})

    monkeypatch.setattr(oidc.httpx, "post", fake_post)
    settings = get_settings()

    tokens = exchange_code_for_tokens("auth-code", "pkce-verifier")

    assert tokens["id_token"] == "signed.by.google"
    assert sent["url"] == TOKEN_ENDPOINT
    assert sent["data"] == {
        "code": "auth-code",
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": settings.google_redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": "pkce-verifier",
    }


def test_a_token_exchange_that_fails_becomes_an_oidc_error(discovery, monkeypatch):
    def refuse(url, data=None, timeout=None):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(oidc.httpx, "post", refuse)

    with pytest.raises(OidcError) as failure:
        exchange_code_for_tokens("auth-code", "pkce-verifier")

    assert "token exchange failed" in str(failure.value)


def test_a_token_response_without_an_id_token_is_refused(discovery, monkeypatch):
    # Google answers this way for a scope with no openid in it. Reading the
    # access_token as an identity would authenticate nobody in particular.
    monkeypatch.setattr(
        oidc.httpx,
        "post",
        lambda url, data=None, timeout=None: FakeResponse({"access_token": "at"}),
    )

    with pytest.raises(OidcError) as failure:
        exchange_code_for_tokens("auth-code", "pkce-verifier")

    assert "no id_token" in str(failure.value)


# ---------------------------------------------------------------------------
# Leg 3: verifying the id_token
# ---------------------------------------------------------------------------


def test_a_properly_signed_token_yields_the_claims_worth_keeping(
    discovery, google_signs, google_key
):
    identity = verify_id_token(make_id_token(google_key), EXPECTED_NONCE)

    assert identity.subject == "google-subject-1234567890"
    assert identity.email == "student@psu.edu"
    assert identity.name == "Test Student"


def test_a_token_signed_by_anyone_but_google_is_refused(
    discovery, google_signs, impostor_key
):
    # Same claims, same algorithm, a key Google never published.
    forged = make_id_token(impostor_key)

    with pytest.raises(OidcError) as failure:
        verify_id_token(forged, EXPECTED_NONCE)

    assert "verification failed" in str(failure.value)


def test_a_token_minted_for_another_client_is_refused(
    discovery, google_signs, google_key
):
    """The classic OAuth mistake: a real Google token for someone else's app.

    It is signed by Google and passes every other check, so without the
    audience check its holder would be logged in here.
    """
    other_app = make_id_token(google_key, aud="another-app.apps.googleusercontent.com")

    with pytest.raises(OidcError):
        verify_id_token(other_app, EXPECTED_NONCE)


def test_a_replayed_token_from_another_login_attempt_is_refused(
    discovery, google_signs, google_key
):
    replayed = make_id_token(google_key, nonce="nonce-from-an-older-login")

    with pytest.raises(OidcError) as failure:
        verify_id_token(replayed, EXPECTED_NONCE)

    assert "nonce" in str(failure.value)


def test_an_unverified_address_is_dropped_and_the_login_continues(
    discovery, google_signs, google_key
):
    # Google sets this for addresses it has not confirmed. Storing one would
    # let a caller claim an identity they do not control.
    unconfirmed = make_id_token(google_key, email_verified=False)

    identity = verify_id_token(unconfirmed, EXPECTED_NONCE)

    assert identity.email is None
    assert identity.subject == "google-subject-1234567890"
