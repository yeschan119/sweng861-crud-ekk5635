"""Rate limiting and suspicious-activity logging.

The login endpoints are the cheapest thing to attack in this application: they
are unauthenticated by definition, and each call costs an outbound request to
Google. A sliding window per client address caps that, and the same counters
give the security log something to summarize.

Deliberately in-process. It is honest about its limit: with more than one
worker each worker keeps its own counters, so the effective ceiling is the
configured one multiplied by the worker count. Making the limit exact means
moving the counters to a shared store such as Redis, which belongs with the
Week 6 deployment work rather than here.
"""

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

logger = logging.getLogger("sweng861.security")


@dataclass(frozen=True)
class Limit:
    """At most `max_events` events per `window_seconds` for one key."""

    max_events: int
    window_seconds: int


class SlidingWindow:
    """Counts recent events per key and forgets the rest.

    A sliding window rather than a fixed one: with a fixed window an attacker
    sends the full allowance just before the boundary and again just after,
    passing at twice the intended rate.
    """

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def record(self, key: str, limit: Limit) -> tuple[bool, int, int]:
        """Record one event. Returns (allowed, count_in_window, retry_after)."""
        now = time.monotonic()
        cutoff = now - limit.window_seconds
        events = self._events[key]

        # Drop what has aged out. Keys whose events have all expired are
        # removed, so an address seen once does not occupy memory forever -
        # unbounded keys would turn this defense into a memory exhaustion
        # vector of its own.
        while events and events[0] <= cutoff:
            events.popleft()
        if not events:
            del self._events[key]
            events = self._events[key]

        if len(events) >= limit.max_events:
            retry_after = max(1, int(events[0] + limit.window_seconds - now) + 1)
            return False, len(events), retry_after

        events.append(now)
        return True, len(events), 0


# One window per concern, so a burst of failed API calls cannot consume the
# allowance for starting a login.
_login_window = SlidingWindow()
_failed_auth_window = SlidingWindow()

LOGIN_LIMIT = Limit(max_events=10, window_seconds=60)
FAILED_AUTH_LIMIT = Limit(max_events=20, window_seconds=60)


def client_key(request: Request) -> str:
    """The address to count against.

    request.client.host is the peer this process is actually talking to. The
    X-Forwarded-For header is not read: a client can send any value it likes,
    so trusting it here would let an attacker reset their own counter by
    changing one header. Behind a proxy this needs uvicorn's --proxy-headers
    with the proxy's address configured as trusted, which is a deployment
    decision for Week 6.
    """
    return request.client.host if request.client else "unknown"


def limit_login(request: Request) -> None:
    """Dependency: cap how often one address can start a login."""
    key = client_key(request)
    allowed, count, retry_after = _login_window.record(key, LOGIN_LIMIT)

    if not allowed:
        logger.warning(
            "rate limit exceeded: %s login attempts from %s within %ss",
            count,
            key,
            LOGIN_LIMIT.window_seconds,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Slow down and try again shortly",
            headers={"Retry-After": str(retry_after)},
        )


def note_failed_authentication(request: Request) -> None:
    """Record a rejected token and warn when one address keeps failing.

    Not an enforcement point - the request has already been refused. This is
    the "log and summarize suspicious activity" half: one 401 is noise, twenty
    from one address in a minute is someone working through tokens, and that
    is the line the log should carry.
    """
    key = client_key(request)
    allowed, count, _ = _failed_auth_window.record(key, FAILED_AUTH_LIMIT)

    if not allowed:
        logger.warning(
            "suspicious activity: %s or more rejected tokens from %s within %ss",
            count,
            key,
            FAILED_AUTH_LIMIT.window_seconds,
        )
    else:
        # Detail stays server-side; the client is told nothing beyond its 401.
        logger.info("rejected token from %s (%s in the last %ss)", key, count,
                    FAILED_AUTH_LIMIT.window_seconds)
