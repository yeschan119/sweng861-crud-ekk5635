"""Google's OpenID Connect provider metadata.

The authorization, token, and JWKS URLs are not hardcoded. Every OIDC provider
publishes them in a discovery document at a well-known address, and reading
them from there means this code keeps working when Google moves an endpoint —
and that the same three lines would point at a different provider by changing
one URL.

Fetched once per process: the document is effectively static, and a login
should not pay for an extra round trip every time.
"""

import secrets
from dataclasses import dataclass
from functools import lru_cache

import httpx
import jwt

from config import get_settings

GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"


@dataclass(frozen=True)
class ProviderMetadata:
    """The four values of the discovery document this application uses."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str


@lru_cache(maxsize=1)
def get_provider_metadata() -> ProviderMetadata:
    response = httpx.get(GOOGLE_DISCOVERY_URL, timeout=10.0)
    response.raise_for_status()
    document = response.json()
    return ProviderMetadata(
        issuer=document["issuer"],
        authorization_endpoint=document["authorization_endpoint"],
        token_endpoint=document["token_endpoint"],
        jwks_uri=document["jwks_uri"],
    )


@dataclass(frozen=True)
class GoogleIdentity:
    """The verified claims this application keeps from an id_token."""

    subject: str
    email: str | None
    name: str | None


class OidcError(Exception):
    """Raised when Google's response cannot be trusted or cannot be read.

    Callers turn this into a generic client-facing message. The detail is for
    the server log; telling a caller which step failed hands an attacker a
    probe.
    """


@lru_cache(maxsize=1)
def _jwks_client() -> jwt.PyJWKClient:
    """Fetches and caches Google's public signing keys.

    Google rotates these keys, and the client re-fetches when an id_token is
    signed with a key id it has not seen, so the cache cannot go stale in a way
    that rejects valid tokens.
    """
    return jwt.PyJWKClient(get_provider_metadata().jwks_uri)


def exchange_code_for_tokens(code: str, code_verifier: str) -> dict:
    """Leg 2: trade the authorization code for tokens.

    This is a direct back-channel POST from this server to Google, carrying the
    client secret. The code travelled through the user's browser; the secret
    never does, which is the reason the authorization code flow exists rather
    than handing tokens straight to the browser.

    The PKCE verifier is sent here in the clear, and that is the point: leg 1
    published only its SHA-256 hash. Google recomputes the hash and compares.
    Whoever redeems the code has to prove they are the party that started the
    flow, so a code intercepted in the browser - in a log, a Referer header, a
    malicious app registered for the same redirect - is useless on its own.
    """
    settings = get_settings()
    try:
        response = httpx.post(
            get_provider_metadata().token_endpoint,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                # Must be byte-for-byte the redirect_uri sent in leg 1. Google
                # compares them to prove the same client started the flow.
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            },
            timeout=10.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise OidcError(f"token exchange failed: {exc}") from exc

    tokens = response.json()
    if "id_token" not in tokens:
        raise OidcError("token response contained no id_token")
    return tokens


def verify_id_token(id_token: str, expected_nonce: str) -> GoogleIdentity:
    """Verify the id_token and return the claims worth keeping.

    An id_token is a JWT signed by Google. Reading its payload without
    verifying it would accept anything a caller typed by hand, so four things
    are checked before a single claim is trusted:

    * signature - against Google's published public key for the token's kid,
      which is what proves Google issued it;
    * issuer - the token really came from accounts.google.com;
    * audience - it was minted for *this* client_id. Skipping this is the
      classic OAuth mistake: a valid Google token issued to some other
      application would otherwise log its holder in here;
    * expiry - enforced by PyJWT, along with requiring the claims to be present
      rather than silently treating a missing one as acceptable.

    The nonce is checked separately, after the signature. It binds this token
    to this browser's login attempt: the value was generated in leg 1, kept in
    a cookie, and echoed by Google into the token. A previously issued, still
    valid id_token replayed here carries some other nonce and is refused.
    """
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=get_settings().google_client_id,
            issuer=get_provider_metadata().issuer,
            options={"require": ["exp", "iat", "iss", "aud", "sub", "nonce"]},
        )
    except (jwt.PyJWTError, httpx.HTTPError) as exc:
        raise OidcError(f"id_token verification failed: {exc}") from exc

    # compare_digest rather than == so the check does not leak, through timing,
    # how much of a guessed nonce was correct.
    if not secrets.compare_digest(claims["nonce"], expected_nonce):
        raise OidcError("id_token nonce did not match the login attempt")

    # Google sets email_verified=false for addresses it has not confirmed.
    # Storing an unverified address would let someone claim an identity they do
    # not control, so the login proceeds on the subject alone and the address is
    # dropped.
    email = claims.get("email") if claims.get("email_verified") else None

    return GoogleIdentity(
        subject=claims["sub"],
        email=email,
        name=claims.get("name"),
    )
