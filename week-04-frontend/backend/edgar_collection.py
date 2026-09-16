"""Choosing which reported figures to keep, and writing them down.

The client fetches, the schemas check the shape, and this module makes the two
judgements that are left: which of the hundreds of facts in a document belong
in the table, and what happens when one is already there.

Selecting annual figures is not a matter of reading a label. A fact carries
``fp``, and it is tempting to read ``fp == "FY"`` as "covers the fiscal year".
It does not. It means "reported in the annual filing", and an annual report
prints the year's quarters alongside the year: of Tesla's 131 NetIncomeLoss
facts marked 10-K and FY, 83 cover 89 to 91 days. The test for annual is
therefore the length of the period itself, which is why the schema keeps
``period_start`` - it is the evidence, not decoration.

Choosing between duplicates is the second judgement. A 10-K restates the prior
year, so the same fiscal year arrives again in every later annual filing under
a new accession number and sometimes with a different value: Tesla filed FY2014
assets as 5,849,251,000 and then as 5,830,667,000 a year later. Only one of
those belongs in a row keyed by period, and it is the later one - a restatement
is the filer correcting itself. Amendments need no special case, because
"filed most recently" already describes them.

The write is an upsert guarded by that same rule. Collecting twice must not
duplicate rows, which the unique key alone would give; it must also not let the
order of two collections decide which figure survives, which is why an older
filing is refused rather than merely deduplicated.

AI use: drafted with Claude against captured documents from a live filer.
"""

import logging
from datetime import date

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

import edgar
from edgar_schemas import EdgarFact, EdgarValidationError, parse_company_concept
from models import Coverage, CoverageFinancial

logger = logging.getLogger("sweng861.edgar.collection")

# Filings made for a fiscal year. A 10-Q covers a quarter and a current report
# or proxy statement is not made for a period at all - those are exactly the
# filings on which EDGAR leaves fy and fp null.
ANNUAL_FORMS = frozenset({"10-K", "10-K/A"})

# A fiscal year is not always 365 days: filers use 52- and 53-week years, so
# Tesla's run 364 or 365 and Apple's vary by a few days either way. The
# threshold only has to separate a year from a quarter, and the widest quarter
# measured is 91 days.
MIN_ANNUAL_DAYS = 350

# Recorded on every row, so the table does not silently come to mean "whatever
# was collected from wherever" if a second provider is added.
SOURCE = "sec_edgar"


def _is_annual(fact: EdgarFact) -> bool:
    """Whether this fact reports a full fiscal year.

    An instant concept - a balance such as Assets - has no period to measure,
    and the annual filing reports it at the year end, so form is the whole test
    for those. A duration concept has to be measured.
    """
    if fact.form not in ANNUAL_FORMS:
        return False
    if fact.start is None:
        return True
    return (fact.end - fact.start).days >= MIN_ANNUAL_DAYS


def select_annual_facts(concept) -> list[EdgarFact]:
    """The annual figures worth storing: one per fiscal year, latest filing.

    Returns them ordered by period so that a caller writing rows, or a reader
    looking at a screenshot of them, sees a time series rather than the order
    EDGAR happened to use.
    """
    latest: dict[date, EdgarFact] = {}
    for fact in concept.facts:
        if not _is_annual(fact):
            continue
        held = latest.get(fact.end)
        if held is None or fact.filed > held.filed:
            latest[fact.end] = fact
    return sorted(latest.values(), key=lambda fact: fact.end)


def collect_concept(
    db: Session,
    coverage: Coverage,
    concept: str,
    *,
    client=None,
) -> int:
    """Fetch one concept for one coverage, validate it, and store the annual facts.

    Returns how many rows the collection covers. Zero means the filer has never
    reported this concept, which EDGAR answers with a 404 and which is an
    ordinary outcome rather than a failure.

    Raises ``EdgarValidationError`` if the document is not what it claims to
    be, and ``EdgarUnavailable`` or ``EdgarResponseError`` if the fetch itself
    failed. Nothing is written on any of those paths: the fetch and the check
    both complete before the first row is built.
    """
    payload = edgar.fetch_company_concept(coverage.cik, concept, client=client)
    if payload is None:
        logger.info(
            "concept not reported coverage_id=%s cik=%s concept=%s",
            coverage.id, coverage.cik, concept,
        )
        return 0

    try:
        document = parse_company_concept(payload)
    except EdgarValidationError:
        # Logged here rather than only at the edge. By the time this reaches a
        # request handler the response body is gone, and which filer and which
        # concept produced a bad document is the part worth keeping - the
        # message names the failing field, and it goes to the log rather than
        # to any client.
        logger.warning(
            "validation failed coverage_id=%s cik=%s concept=%s",
            coverage.id, coverage.cik, concept, exc_info=True,
        )
        raise

    # The response has to be about the filer that was asked for. A mismatch
    # would mean a row filed under the wrong company, which no later check
    # would catch because the number itself is perfectly valid.
    if document.padded_cik != coverage.cik:
        raise EdgarValidationError(
            f"document is for CIK{document.padded_cik}, "
            f"expected CIK{coverage.cik}"
        )

    facts = select_annual_facts(document)
    if not facts:
        logger.info(
            "no annual figures coverage_id=%s concept=%s facts=%s",
            coverage.id, concept, len(document.facts),
        )
        return 0

    _upsert(db, coverage, concept, facts)
    logger.info(
        "collected coverage_id=%s concept=%s rows=%s", coverage.id, concept, len(facts)
    )
    return len(facts)


def _upsert(
    db: Session, coverage: Coverage, concept: str, facts: list[EdgarFact]
) -> None:
    """Write the facts, letting a repeat collection update rather than duplicate.

    One statement rather than a read followed by an insert or an update. The
    read-then-write shape has a window between the two in which another
    collection can insert the same row, and the unique key would turn that into
    an error a user did nothing to deserve.

    The WHERE clause on the update is what makes the result independent of the
    order two collections happen to run in. Without it, re-collecting an older
    snapshot would walk a restated figure back to the one it superseded, and
    nothing about the resulting row would look wrong.
    """
    rows = [
        {
            "coverage_id": coverage.id,
            "concept": concept,
            "period_end": fact.end,
            "period_start": fact.start,
            "value": fact.val,
            "unit": "USD",
            "form": fact.form,
            "accn": fact.accn,
            "filed": fact.filed,
            "fiscal_year": fact.fy,
            "fiscal_period": fact.fp,
            "source": SOURCE,
        }
        for fact in facts
    ]

    statement = insert(CoverageFinancial).values(rows)
    db.execute(
        statement.on_conflict_do_update(
            constraint="uq_coverage_financials_period",
            set_={
                "period_start": statement.excluded.period_start,
                "value": statement.excluded.value,
                "form": statement.excluded.form,
                "accn": statement.excluded.accn,
                "filed": statement.excluded.filed,
                "fiscal_year": statement.excluded.fiscal_year,
                "fiscal_period": statement.excluded.fiscal_period,
                "collected_at": statement.excluded.collected_at,
            },
            where=statement.excluded.filed >= CoverageFinancial.filed,
        )
    )
    db.flush()


def collect_coverage(db: Session, coverage: Coverage, *, client=None) -> dict[str, int]:
    """Collect every concept this application tracks for one coverage.

    Returns how many rows each concept contributed, keyed by the tag actually
    stored. A concept the filer never reported is absent rather than zero: the
    caller asked what was collected, and "nothing, because they do not report
    it" is not a row count.

    Revenue is a chain rather than a tag. ASC 606 replaced Revenues with
    RevenueFromContractWithCustomerExcludingAssessedTax for most filers from
    2018, but not for all of them and not at the same time - JPMorgan still
    reports the older tag and answers 404 for the newer one, while Apple
    answers 200 for the older one with figures that stop in 2018. The first tag
    that yields annual figures wins, and the tag that won is what gets stored,
    so a row can be traced to the concept it actually came from.

    The chain stops at the first hit rather than merging both tags into one
    series. Merging would mean deciding, year by year, which of two disagreeing
    tags to believe, and the newer tag already covers every year a filer has
    reported under it.

    An error from any concept aborts the whole collection. Half a series is
    worse than none: it looks complete to whoever reads it next.
    """
    collected: dict[str, int] = {}

    for concept in edgar.REVENUE_CONCEPTS:
        rows = collect_concept(db, coverage, concept, client=client)
        if rows:
            collected[concept] = rows
            break

    for concept in (
        edgar.NET_INCOME_CONCEPT,
        edgar.ASSETS_CONCEPT,
        edgar.EQUITY_CONCEPT,
    ):
        rows = collect_concept(db, coverage, concept, client=client)
        if rows:
            collected[concept] = rows

    return collected
