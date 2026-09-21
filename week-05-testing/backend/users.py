"""Reading and writing the local user record.

Kept out of the route so the callback reads as the OAuth flow it is, and so
this rule - one Google account is one row, found by subject - has a single
place to live.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import User
from oidc import GoogleIdentity


def upsert_user(session: Session, identity: GoogleIdentity) -> User:
    """Return the row for this Google account, creating it on first login.

    Looked up by subject, never by email: the subject is the identifier Google
    promises is stable, and it is what makes a returning user the same user
    rather than a second account.

    Profile fields are refreshed on every login so a changed address or display
    name does not go stale, and last_login_at is stamped either way - it is the
    one field that is interesting even when nothing else moved.
    """
    user = session.scalar(select(User).where(User.google_sub == identity.subject))

    if user is None:
        user = User(google_sub=identity.subject)
        session.add(user)

    user.email = identity.email
    user.name = identity.name
    user.last_login_at = datetime.now(timezone.utc)

    session.commit()
    session.refresh(user)
    return user
