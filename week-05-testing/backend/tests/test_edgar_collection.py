"""Selecting figures out of an EDGAR document, and writing them down.

Two halves, tested apart. Selection is a pure function over a captured
document, so it needs neither a network nor a database and the numbers it is
asserted against are real ones a filer actually reported. Persistence needs a
database and is marked so, because those tests describe what a constraint does
rather than what a function returns.

The captured documents are the point. Every expected value below was reported
by Tesla to the SEC, which means a test failing here is either a real
regression or EDGAR changing its data - and not an invented fixture drifting
away from a live API that never agreed with it.
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from conftest import needs_db

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture(scope="session")
def tesla_assets() -> dict:
    """Assets: an instant concept, so no fact carries a period start.

    124 facts covering 10-K, 10-K/A and 10-Q, which is what makes it worth
    keeping: the form filter, the amendment tie-break and the annual selection
    are all exercised by one real document.
    """
    return load("tesla_assets_200.json")


@pytest.fixture(scope="session")
def tesla_netincome() -> dict:
    """NetIncomeLoss: a duration concept, and the reason fp is not trusted.

    131 of its facts carry form 10-K and fp "FY". Only 48 of those cover a
    year; the rest are the quarters printed inside the annual report.
    """
    return load("tesla_netincome_200.json")


# --------------------------------------------------------------------------
# Selection - pure, no database, no network
# --------------------------------------------------------------------------


def test_one_row_per_period_end(tesla_assets):
    """32 annual facts collapse to the 16 fiscal years they describe.

    A 10-K restates the prior year, so the same year arrives again in each
    later filing under a new accession number. Keying on the accession number
    would keep all 32.
    """
    from edgar_collection import select_annual_facts
    from edgar_schemas import parse_company_concept

    facts = select_annual_facts(parse_company_concept(tesla_assets))

    ends = [f.end for f in facts]
    assert len(ends) == len(set(ends)), "a fiscal year appears more than once"
    assert len(facts) == 16


def test_restated_value_wins(tesla_assets):
    """Tesla filed FY2014 assets twice, and the second time it was different.

    5,849,251,000 in the 2015 filing, 5,830,667,000 in the 2016 one. The later
    filing is the company correcting itself, so it is the one to keep.
    """
    from edgar_collection import select_annual_facts
    from edgar_schemas import parse_company_concept

    facts = {f.end: f for f in select_annual_facts(parse_company_concept(tesla_assets))}

    fy2014 = facts[date(2014, 12, 31)]
    assert fy2014.val == Decimal("5830667000")
    assert fy2014.filed == date(2016, 2, 24)


def test_amendment_wins_when_filed_later(tesla_assets):
    """FY2010 was filed on a 10-K and again three weeks later on a 10-K/A.

    Nothing special is done for amendments: the same "latest filing wins" rule
    picks it, because that is what an amendment is.
    """
    from edgar_collection import select_annual_facts
    from edgar_schemas import parse_company_concept

    facts = {f.end: f for f in select_annual_facts(parse_company_concept(tesla_assets))}

    assert facts[date(2010, 12, 31)].form == "10-K/A"


def test_quarterly_periods_inside_an_annual_report_are_not_annual(tesla_netincome):
    """fp="FY" means "reported in the annual filing", not "covers the year".

    131 facts carry an annual form and fp FY. 83 of them are quarters printed
    inside that report, and storing those as annual figures would trip the
    unique key against the real year and quietly keep the wrong one.
    """
    from edgar_collection import ANNUAL_FORMS, MIN_ANNUAL_DAYS, select_annual_facts
    from edgar_schemas import parse_company_concept

    concept = parse_company_concept(tesla_netincome)
    labelled_annual = [
        f for f in concept.facts if f.form in ANNUAL_FORMS and f.fp == "FY"
    ]
    facts = select_annual_facts(concept)

    assert len(labelled_annual) == 131
    assert len(facts) == 17
    for fact in facts:
        assert (fact.end - fact.start).days >= MIN_ANNUAL_DAYS


def test_quarterly_filings_are_excluded(tesla_assets):
    """92 of the 124 facts come from a 10-Q. None of them is stored."""
    from edgar_collection import select_annual_facts
    from edgar_schemas import parse_company_concept

    facts = select_annual_facts(parse_company_concept(tesla_assets))

    assert {f.form for f in facts} <= {"10-K", "10-K/A"}


# --------------------------------------------------------------------------
# Validation - a bad document must not reach the database
# --------------------------------------------------------------------------


@needs_db
def test_a_malformed_document_is_refused_and_written_nowhere(db_session, coverage, caplog):
    """Issue #7: validation failures are logged and never reach the database.

    The document is a real one with one field broken, rather than a hand-built
    object, so what is being tested is the response actually parsed minus the
    single property under test.
    """
    from edgar_collection import collect_concept
    from edgar_schemas import EdgarValidationError
    from models import CoverageFinancial

    broken = load("tesla_assets_200.json")
    broken["units"]["USD"][0]["val"] = "not a number"
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=broken))
    )

    with pytest.raises(EdgarValidationError):
        collect_concept(db_session, coverage, "Assets", client=client)

    assert db_session.query(CoverageFinancial).count() == 0
    assert "validation" in caplog.text.lower()


@needs_db
def test_a_concept_the_filer_never_reported_writes_nothing(db_session, coverage):
    """Issue #7: the 404 path, driven by the body EDGAR actually returns.

    The captured response is XML, not JSON, which is the whole reason the
    client reads the status code before the body. A "not reported" is a fact
    about the company, so it is an empty result rather than an exception.
    """
    from edgar_collection import collect_concept
    from models import CoverageFinancial

    body = (FIXTURES / "jpmorgan_revenue_404.xml").read_bytes()
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(404, content=body, headers={"Content-Type": "application/xml"})
        )
    )

    written = collect_concept(db_session, coverage, "Assets", client=client)

    assert written == 0
    assert db_session.query(CoverageFinancial).count() == 0


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------


@needs_db
def test_what_was_written(db_session, coverage, assets_client):
    """Issue #7: one test confirming what reached the table.

    Asserted against Tesla's most recent annual balance rather than against
    whatever the code produced.
    """
    from edgar_collection import SOURCE, collect_concept
    from models import CoverageFinancial

    collect_concept(db_session, coverage, "Assets", client=assets_client)

    row = (
        db_session.query(CoverageFinancial)
        .filter_by(concept="Assets", period_end=date(2025, 12, 31))
        .one()
    )
    assert row.coverage_id == coverage.id
    assert row.value == Decimal("137806000000")
    assert row.period_start is None          # an instant concept
    assert row.unit == "USD"
    assert row.form == "10-K"
    assert row.filed == date(2026, 1, 29)
    assert row.accn                           # traceable back to a filing
    assert row.source == SOURCE
    assert row.collected_at is not None


@needs_db
def test_collecting_the_same_payload_twice_does_not_duplicate(db_session, coverage, assets_client):
    """Issue #7: repeat collection is an update, not a second set of rows."""
    from edgar_collection import collect_concept
    from models import CoverageFinancial

    first = collect_concept(db_session, coverage, "Assets", client=assets_client)
    second = collect_concept(db_session, coverage, "Assets", client=assets_client)

    assert first == 16
    assert second == 16
    assert db_session.query(CoverageFinancial).count() == 16


@needs_db
def test_a_later_filing_replaces_the_value(db_session, coverage, assets_client):
    """A restatement collected afterwards overwrites what was stored."""
    from edgar_collection import collect_concept
    from models import CoverageFinancial

    stale = load("tesla_assets_200.json")
    stale["units"]["USD"] = [
        f for f in stale["units"]["USD"] if f["filed"] < "2016-01-01"
    ]
    stale_client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=stale))
    )

    collect_concept(db_session, coverage, "Assets", client=stale_client)
    before = db_session.query(CoverageFinancial).filter_by(
        concept="Assets", period_end=date(2014, 12, 31)
    ).one()
    assert before.value == Decimal("5849251000")

    db_session.expire_all()
    collect_concept(db_session, coverage, "Assets", client=assets_client)

    after = db_session.query(CoverageFinancial).filter_by(
        concept="Assets", period_end=date(2014, 12, 31)
    ).one()
    assert after.value == Decimal("5830667000")


@needs_db
def test_an_older_filing_does_not_overwrite_a_newer_one(db_session, coverage, assets_client):
    """Collection order must not decide which figure survives.

    Without the guard, re-running a collection against an older snapshot would
    silently walk the restated value back to the superseded one.
    """
    from edgar_collection import collect_concept
    from models import CoverageFinancial

    stale = load("tesla_assets_200.json")
    stale["units"]["USD"] = [
        f for f in stale["units"]["USD"] if f["filed"] < "2016-01-01"
    ]
    stale_client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=stale))
    )

    collect_concept(db_session, coverage, "Assets", client=assets_client)
    db_session.expire_all()
    collect_concept(db_session, coverage, "Assets", client=stale_client)

    row = db_session.query(CoverageFinancial).filter_by(
        concept="Assets", period_end=date(2014, 12, 31)
    ).one()
    assert row.value == Decimal("5830667000")
