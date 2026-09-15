"""Configuration read from the environment.

Secrets never live in source. The Google client secret and the session signing
key are read from `.env`, which `.gitignore` excludes; `.env.example` documents
the variable names with placeholder values so the app can be set up from a
clean checkout.

Loading fails loudly at startup when a variable is missing. A missing client
secret should stop the process, not surface later as a confusing 400 from
Google's token endpoint.
"""

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            "Copy .env.example to .env and fill it in."
        )
    return value


@dataclass(frozen=True)
class Settings:
    """Every value the auth layer needs, resolved once and then read-only."""

    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str
    session_jwt_secret: str
    session_jwt_ttl_seconds: int
    database_url: str
    sec_user_agent: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Build the settings once per process.

    Cached rather than module-level so that importing this module has no side
    effects: tests can import the app without a fully populated .env.
    """
    return Settings(
        google_client_id=_required("GOOGLE_CLIENT_ID"),
        google_client_secret=_required("GOOGLE_CLIENT_SECRET"),
        google_redirect_uri=_required("GOOGLE_REDIRECT_URI"),
        session_jwt_secret=_required("SESSION_JWT_SECRET"),
        session_jwt_ttl_seconds=int(os.getenv("SESSION_JWT_TTL_SECONDS", "3600")),
        database_url=_required("DATABASE_URL"),
        sec_user_agent=_required("SEC_USER_AGENT"),
    )
