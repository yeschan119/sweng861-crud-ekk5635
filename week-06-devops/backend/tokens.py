"""The session token this application issues to its own clients.

Google's id_token proves who the user is; it is not this application's session
credential. It is minted for the login exchange, it carries Google's lifetime
and Google's claims, and passing it around as an API credential would mean
every protected route re-validating a third party's token. So the login ends
by issuing a token of our own, and the API only ever accepts that.
"""

from datetime import datetime, timedelta, timezone

import jwt

from config import get_settings
from models import User

# Names this application as the issuer of its own tokens, so a token from some
# other system that happens to be signed with a leaked key still fails.
ISSUER = "sweng861-week2-auth"

ALGORITHM = "HS256"


def issue_session_token(user: User) -> str:
    """Sign a JWT that identifies this user to this API.

    The subject is the local user id, not the Google subject. Downstream code
    - the Week 3 owner_id checks in particular - reasons in this application's
    identifiers, and a token that speaks Google's would push that translation
    into every handler.

    The payload carries only what a request needs: subject, email for the
    greeting, and the standard time claims. Name, picture, and Google's other
    profile claims are left out; a JWT is signed, not encrypted, so anything
    put in it is readable by anyone holding it.

    HS256 because one service both signs and verifies. Asymmetric signing earns
    its complexity when a party that must not be able to mint tokens needs to
    verify them, which is not the case here.
    """
    settings = get_settings()
    issued_at = datetime.now(timezone.utc)

    payload = {
        "iss": ISSUER,
        "sub": str(user.id),
        "email": user.email,
        "iat": issued_at,
        "exp": issued_at + timedelta(seconds=settings.session_jwt_ttl_seconds),
    }
    return jwt.encode(payload, settings.session_jwt_secret, algorithm=ALGORITHM)
