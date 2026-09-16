"""Part C behaviour: /api/hello is closed without a valid token and open with one."""

import base64
import json
import time

import jwt
import pytest

from tokens import ALGORITHM, ISSUER

UNAUTHORIZED_BODY = {
    "error": "Unauthorized",
    "message": "Valid access token is required",
}

SECRET = "test-signing-key-used-only-by-the-test-suite"


def test_unauthenticated_request_is_rejected(client):
    """The first required test: no token means 401."""
    response = client.get("/api/hello")

    assert response.status_code == 401
    assert response.json() == UNAUTHORIZED_BODY
    # RFC 6750: the resource states how to authenticate.
    assert response.headers["www-authenticate"] == "Bearer"


def test_authenticated_request_succeeds(client, valid_token):
    """The second required test: a valid token means 200 and the greeting."""
    response = client.get(
        "/api/hello", headers={"Authorization": f"Bearer {valid_token}"}
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Hello, student@psu.edu!"}


def test_health_stays_public(client):
    """The liveness probe must not require a login."""
    assert client.get("/health").status_code == 200


def _tampered_token() -> str:
    """A valid token whose payload claims a different user, signature untouched."""
    valid = jwt.encode(
        {
            "iss": ISSUER,
            "sub": "7",
            "email": "student@psu.edu",
            "iat": int(time.time()),
            "exp": int(time.time()) + 600,
        },
        SECRET,
        algorithm=ALGORITHM,
    )
    header, payload, signature = valid.split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
    claims["sub"] = "999"
    forged = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"{header}.{forged}.{signature}"


@pytest.mark.parametrize(
    "label, token",
    [
        (
            "expired",
            jwt.encode(
                {"iss": ISSUER, "sub": "7", "iat": int(time.time()) - 7200,
                 "exp": int(time.time()) - 3600},
                SECRET, algorithm=ALGORITHM,
            ),
        ),
        (
            "signed with another key",
            jwt.encode(
                {"iss": ISSUER, "sub": "7", "iat": int(time.time()),
                 "exp": int(time.time()) + 600},
                "an-attackers-key", algorithm=ALGORITHM,
            ),
        ),
        (
            "issued by someone else",
            jwt.encode(
                {"iss": "https://evil.example", "sub": "7", "iat": int(time.time()),
                 "exp": int(time.time()) + 600},
                SECRET, algorithm=ALGORITHM,
            ),
        ),
        (
            "no expiry",
            jwt.encode(
                {"iss": ISSUER, "sub": "7", "iat": int(time.time())},
                SECRET, algorithm=ALGORITHM,
            ),
        ),
        (
            "alg=none",
            jwt.encode(
                {"iss": ISSUER, "sub": "7", "iat": int(time.time()),
                 "exp": int(time.time()) + 600},
                key="", algorithm="none",
            ),
        ),
        ("payload edited to another user", _tampered_token()),
        ("not a token at all", "hello"),
    ],
)
def test_bad_tokens_are_rejected(client, label, token):
    """Every rejection looks the same from outside; only the log knows why."""
    response = client.get("/api/hello", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401, label
    assert response.json() == UNAUTHORIZED_BODY, label
