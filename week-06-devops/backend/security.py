"""The reusable authentication gate for protected endpoints.

Written as a FastAPI dependency rather than ASGI middleware. Middleware runs on
every request, so protecting one route with it means the middleware itself
deciding which paths are exempt - a list that quietly rots as routes are added,
and whose default is "open". A dependency is declared on the routes that need
it, so a protected route cannot forget to be protected, and it hands the
handler a typed user instead of an untyped value on the request object.
"""

from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import get_settings
from db import get_db
from models import User, UserRole
from ratelimit import note_failed_authentication
from tokens import ALGORITHM, ISSUER


@dataclass(frozen=True)
class AuthenticatedUser:
    """Who the caller is, according to their own token.

    Deliberately thin: the local user id and the email claim, which is all any
    Week 2 handler needs. Loading the database row here would mean a query on
    every request to fetch fields nothing reads.
    """

    id: int
    email: str | None


# auto_error=False so a missing header reaches this code and produces the
# error body the assignment specifies, instead of FastAPI's default shape.
_bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    """One 401 for every reason.

    Missing header, malformed token, bad signature, expired, wrong issuer - the
    caller is told the same thing each time. Explaining which check failed
    tells an attacker whether a token was genuine but stale, or forged.
    """
    return HTTPException(
        # Only the message. The "error" key and the status phrase beside it are
        # filled in by errors.py, so the shape is decided in one place.
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Valid access token is required",
        # RFC 6750: a 401 from a bearer-protected resource says how to authenticate.
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> AuthenticatedUser:
    """Verify the bearer token and return the caller's identity.

    The signature check is what makes the claims trustworthy: the payload of a
    JWT is base64, not ciphertext, so a caller can edit "sub" to any user id
    they like. Only the HMAC over the payload, which they cannot recompute
    without the signing key, decides whether those claims are ours.

    The issuer is pinned and the standard claims are required, so a token
    signed elsewhere, or one missing an expiry, is not accepted by default.

    Every rejection is reported to the security log, which is what turns a
    single 401 into a visible pattern when one address produces many.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        note_failed_authentication(request)
        raise _unauthorized()

    try:
        claims = jwt.decode(
            credentials.credentials,
            get_settings().session_jwt_secret,
            algorithms=[ALGORITHM],
            issuer=ISSUER,
            options={"require": ["exp", "iat", "iss", "sub"]},
        )
    except jwt.PyJWTError:
        note_failed_authentication(request)
        raise _unauthorized() from None

    return AuthenticatedUser(id=int(claims["sub"]), email=claims.get("email"))


def require_admin(
    user: AuthenticatedUser = Depends(require_auth),
    db: Session = Depends(get_db),
) -> AuthenticatedUser:
    """Admit only an administrator, asking the database each time.

    Layered on require_auth rather than repeating it: the token is verified
    once, by the code that owns that job, and this dependency answers the one
    question left - is this caller an administrator?

    The role is read here instead of being carried in the token. A token is a
    bearer credential that stays valid until it expires, so a role minted into
    one would outlive the decision that granted it: an administrator demoted a
    minute after signing in would keep administering for the rest of the hour.
    The column is the system of record, and reading it costs a query only on
    the routes that need one.

    A caller whose row is gone is not an administrator either. That is the
    whole of the reasoning - this dependency answers yes or no, and a missing
    row is a no. Turning it into a 401 would mean second-guessing require_auth,
    which has already accepted the token.
    """
    role = db.scalar(select(User.role).where(User.id == user.id))

    if role != UserRole.ADMIN.value:
        # 403, not the 404 a cross-tenant request gets. Those two hide
        # different things. A 404 hides which rows exist, because an id that
        # answers differently is an id an attacker can enumerate. An admin
        # route hides nothing: it is one fixed path, the same for everyone, and
        # it is in the published OpenAPI document. Answering 404 there would
        # only tell an administrator who had just lost the role that the
        # feature had been removed.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint requires the admin role",
        )

    return user
