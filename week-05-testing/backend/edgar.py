"""SEC EDGAR — the third-party API this service reads company financials from.

Part 1 asks for a public JSON API, consumed with timeouts, retries and error
handling. This module is the transport half of that: it turns a filer and an
accounting concept into a parsed response, or into a typed failure. It does not
decide whether the numbers inside are any good — that is validation, and it
lives in its own step so that nothing unchecked can reach the database.

Why this API. EDGAR publishes the XBRL data behind every filing US public
companies make with the SEC, so the figures a coverage row cites are the
primary source rather than someone's copy of it. It is free, needs no account
and no key, is versioned by a regulator rather than by a vendor whose free tier
can disappear mid-semester, and its `companyconcept` endpoint answers with a
small, flat JSON document keyed by unit and period, which is a shape worth
validating rather than a blob worth storing. The trade is that its failure
modes are unusual, and the two that matter were measured, not assumed.

What the probe found, and what it forces this module to do:

*A concept the filer never reported answers 404 with an XML body.* Not an empty
`units` object, and not JSON at all. Handing that body to a parser raises, so
the status code has to be read before the body is touched. A 404 here is a
fact about the company — Tesla files no `Revenues` under that tag — and not an
error, so it comes back as ``None`` rather than as an exception.

*A 200 does not mean the number is current.* Apple answers 200 for `Revenues`
whose most recent annual figure ends 2018-09-29, because the tag was
superseded by `RevenueFromContractWithCustomerExcludingAssessedTax` when
ASC 606 took effect. Choosing between the two, and refusing a stale one, is
validation's problem; this module hands over what EDGAR said.

The outage requirement — "an outage in the third-party API does not take our
endpoints down with a 500" — is met by exhausting every failure into
``EdgarUnavailable`` or ``EdgarResponseError``. Neither escapes as a bare
``httpx`` exception, so no route can leak one into the unhandled-error handler.
Mapping those onto a status code belongs to the endpoint that calls this, which
arrives with persistence.

AI use: drafted with Claude from a captured probe of five filers and seven
concepts.
"""

import logging
import time
from functools import lru_cache
from typing import Any

import httpx

from config import get_settings

logger = logging.getLogger("sweng861.edgar")

BASE_URL = "https://data.sec.gov/api/xbrl/companyconcept"

# US GAAP. EDGAR also serves ifrs-full and dei; a filer indexed under a
# different taxonomy would answer 404 here, which this module already treats as
# "not reported" rather than as a crash.
TAXONOMY = "us-gaap"

# The four figures a coverage collects. Revenue is a chain rather than a single
# tag: ASC 606 replaced `Revenues` for most filers from 2018, but not for all
# of them and not at the same time, so both names have to be asked for and the
# fresher answer taken. Walking the chain is the caller's job — this module
# fetches one concept per call and reports plainly what came back.
REVENUE_CONCEPTS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
)
NET_INCOME_CONCEPT = "NetIncomeLoss"
ASSETS_CONCEPT = "Assets"
EQUITY_CONCEPT = "StockholdersEquity"

# Split rather than a single number: a connection that is refused should be
# given up on quickly, while a request already accepted deserves longer. Both
# are short because a user is waiting on the other end of this call.
TIMEOUT = httpx.Timeout(connect=3.0, read=6.0, write=3.0, pool=3.0)

# Retries are bounded by a clock as well as by a count. A count alone
# multiplies the timeout: three attempts against a black-holed host is three
# read timeouts back to back, and the caller waits the sum. The budget caps
# what the whole call can cost no matter how the attempts fail.
MAX_ATTEMPTS = 3
TOTAL_BUDGET_SECONDS = 15.0
BACKOFF_SECONDS = 0.5

# Retried because they describe the moment, not the request: rate limiting and
# the 5xx family. Every other 4xx is a statement about what was asked for, and
# asking again spends SEC's fair-access budget to be told the same thing.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

# 429 may carry Retry-After. Honoured, but not on the server's word alone: an
# upstream is free to name a delay longer than this request can afford.
MAX_RETRY_AFTER_SECONDS = 5.0


class EdgarError(Exception):
    """Base class for every failure this module reports.

    A caller that wants to treat "EDGAR did not work" as one case catches this;
    one that distinguishes a retryable outage from a broken contract catches
    the two subclasses. What no caller has to handle is an httpx exception,
    because none escapes this module.
    """


class EdgarUnavailable(EdgarError):
    """EDGAR could not be reached, or answered in a way worth retrying later.

    A timeout, a refused connection, or a 5xx or 429 that survived the retries.
    The request itself was fine, so the same call may well succeed later.
    """


class EdgarResponseError(EdgarError):
    """EDGAR answered, but not with something this module can use.

    A status outside the ones expected, or a 200 whose body is not JSON.
    Retrying will produce the same result; something about the request or about
    the contract has changed.
    """


def normalise_cik(cik: str) -> str:
    """Ten digits, zero-padded, the way EDGAR's path segment wants it.

    `coverages.cik` is already CHAR(10) so a stored value arrives correct, but
    this is also the boundary where a hand-typed CIK enters — Apple is as often
    written 320193 as 0000320193 — and a bad path segment would come back as a
    404 that this module reports as "the company does not report that", which
    is the wrong answer to a typo.
    """
    digits = str(cik).strip().upper().removeprefix("CIK").lstrip("-").strip()
    if not digits.isdigit() or len(digits) > 10:
        raise ValueError(f"CIK must be up to ten digits, got {cik!r}")
    return digits.zfill(10)


@lru_cache(maxsize=1)
def _shared_client() -> httpx.Client:
    """One connection pool for the process, built on first use.

    Cached rather than created per call so repeated collections reuse the TLS
    handshake, and lazy rather than module-level so that importing this module
    has no side effects and needs no settings — the same reason
    ``get_settings`` is cached in config.py.
    """
    return httpx.Client(
        timeout=TIMEOUT,
        headers={
            # Required. EDGAR answers 403 to a request that does not name
            # someone to contact about it.
            "User-Agent": get_settings().sec_user_agent,
            "Accept": "application/json",
        },
    )


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """The server's requested delay, if it sent one this module will accept."""
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        # The HTTP-date form is legal too, and ignored here: EDGAR sends
        # seconds, and a date would need clock-skew handling to be worth more
        # than the fixed backoff already in place.
        return min(float(raw), MAX_RETRY_AFTER_SECONDS)
    except ValueError:
        return None


def fetch_company_concept(
    cik: str,
    concept: str,
    *,
    client: httpx.Client | None = None,
) -> dict[str, Any] | None:
    """Fetch one accounting concept for one filer.

    Returns the parsed response, or ``None`` when EDGAR answers 404 — meaning
    this filer has never reported this concept under this taxonomy. That is an
    ordinary outcome and the reason the signal is a return value: an exception
    would push a normal branch into error handling, and the 404 body is XML, so
    a caller that skipped the branch would fail at the parser instead.

    Raises ``EdgarUnavailable`` when the retries are used up on a transport
    failure or a retryable status, and ``EdgarResponseError`` when the answer is
    outside the contract. Nothing else leaves this function.

    Passing ``client`` overrides the shared pool, which is how a test drives
    this against a captured response with no network.
    """
    padded = normalise_cik(cik)
    url = f"{BASE_URL}/CIK{padded}/{TAXONOMY}/{concept}.json"
    http = client or _shared_client()
    deadline = time.monotonic() + TOTAL_BUDGET_SECONDS
    last_reason = "no attempt was made"

    for attempt in range(1, MAX_ATTEMPTS + 1):
        # Reset every iteration: a delay the server asked for on the previous
        # attempt must not be carried into this one.
        requested_delay: float | None = None
        try:
            response = http.get(url)
        except httpx.HTTPError as exc:
            # Covers timeouts, DNS failures and refused connections alike. The
            # type is logged rather than the message: httpx puts the resolved
            # host and port in the text, and this string is on its way to a log
            # that the report will screenshot.
            last_reason = f"transport failure ({type(exc).__name__})"
            logger.warning(
                "edgar attempt %s/%s failed cik=%s concept=%s reason=%s",
                attempt, MAX_ATTEMPTS, padded, concept, last_reason,
            )
        else:
            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError as exc:
                    # A 200 that is not JSON is a contract break, not a blip.
                    raise EdgarResponseError(
                        f"EDGAR returned 200 with an unparsable body for "
                        f"CIK{padded}/{concept}"
                    ) from exc

            if response.status_code == 404:
                # The documented shape of "this filer does not report that".
                # Deliberately not parsed: the body is XML.
                logger.info(
                    "edgar concept not reported cik=%s concept=%s", padded, concept
                )
                return None

            if response.status_code not in RETRYABLE_STATUS:
                # 403 lands here, which is what a missing or rejected
                # User-Agent looks like. Naming the status is enough for the
                # log; the body is the upstream's to describe, not ours.
                raise EdgarResponseError(
                    f"EDGAR answered {response.status_code} for "
                    f"CIK{padded}/{concept}"
                )

            last_reason = f"status {response.status_code}"
            logger.warning(
                "edgar attempt %s/%s failed cik=%s concept=%s reason=%s",
                attempt, MAX_ATTEMPTS, padded, concept, last_reason,
            )
            requested_delay = _retry_after_seconds(response)

        # Reached only when this attempt failed in a retryable way.
        delay = BACKOFF_SECONDS * (2 ** (attempt - 1))
        if requested_delay is not None:
            delay = max(delay, requested_delay)
        remaining = deadline - time.monotonic()
        if attempt == MAX_ATTEMPTS or remaining <= delay:
            break
        time.sleep(delay)

    raise EdgarUnavailable(
        f"EDGAR unreachable for CIK{padded}/{concept} after {attempt} "
        f"attempt(s): {last_reason}"
    )
