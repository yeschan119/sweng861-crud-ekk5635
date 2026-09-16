"""The endpoint that collects external figures, and the one that reads them.

Two things are being asserted here that the collection tests could not.

Ownership: a coverage belonging to someone else must be indistinguishable from
one that does not exist, on both verbs. #10 settled that for coverages, and a
sub-resource is where that rule is easiest to lose, because the id in the path
belongs to the parent.

Containment: an outage at SEC must not become a 500. That was the third thing
issue #6 asked for and the one it could not demonstrate, because nothing called
the client yet. It can be demonstrated now.
"""

import json
from pathlib import Path

import httpx
import pytest

from conftest import needs_db

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def edgar_always_answers(monkeypatch):
    """Every concept resolves to the captured Tesla Assets document."""
    payload = json.loads((FIXTURES / "tesla_assets_200.json").read_text())
    _install(monkeypatch, lambda request: httpx.Response(200, json=payload))


@pytest.fixture
def edgar_is_down(monkeypatch):
    """Every request times out, exhausting the client's retries."""
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("connect timed out")

    _install(monkeypatch, boom)


@pytest.fixture
def edgar_talks_nonsense(monkeypatch):
    """A 200 whose body is not the document it claims to be."""
    broken = json.loads((FIXTURES / "tesla_assets_200.json").read_text())
    broken["units"]["USD"][0]["val"] = "not a number"
    _install(monkeypatch, lambda request: httpx.Response(200, json=broken))


def _install(monkeypatch, handler) -> None:
    """Point the shared client at a mock transport, with no retry delay.

    The backoff is removed as well: exercising an outage should cost the suite
    the assertion, not the fifteen seconds of budget the real client spends
    before it gives up.
    """
    import edgar

    monkeypatch.setattr(edgar, "BACKOFF_SECONDS", 0)
    monkeypatch.setattr(
        edgar,
        "_shared_client",
        lambda: httpx.Client(transport=httpx.MockTransport(handler)),
    )


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------
# Collecting
# --------------------------------------------------------------------------


@needs_db
def test_collection_requires_a_token(api, coverage):
    response = api.post(f"/api/coverages/{coverage.id}/financials")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


@needs_db
def test_collection_writes_rows_and_reports_what_it_did(
    api, coverage, owner_token, edgar_always_answers
):
    response = api.post(
        f"/api/coverages/{coverage.id}/financials", headers=auth(owner_token)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["collected"] == 64          # four concepts, sixteen years each
    assert body["coverage_id"] == coverage.id
    assert sorted(body["concepts"]) == body["concepts"]


@needs_db
def test_collecting_twice_does_not_duplicate(
    api, coverage, owner_token, edgar_always_answers
):
    api.post(f"/api/coverages/{coverage.id}/financials", headers=auth(owner_token))
    api.post(f"/api/coverages/{coverage.id}/financials", headers=auth(owner_token))

    listed = api.get(
        f"/api/coverages/{coverage.id}/financials", headers=auth(owner_token)
    )
    assert len(listed.json()) == 64


@needs_db
def test_collecting_for_someone_elses_coverage_is_a_404(
    api, coverage, other_token, edgar_always_answers
):
    """Byte-identical to an id that does not exist. See #10."""
    theirs = api.post(
        f"/api/coverages/{coverage.id}/financials", headers=auth(other_token)
    )
    missing = api.post("/api/coverages/999999/financials", headers=auth(other_token))

    assert theirs.status_code == 404
    assert theirs.content == missing.content


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------


@needs_db
def test_reading_returns_the_stored_series(
    api, coverage, owner_token, edgar_always_answers
):
    api.post(f"/api/coverages/{coverage.id}/financials", headers=auth(owner_token))

    response = api.get(
        f"/api/coverages/{coverage.id}/financials", headers=auth(owner_token)
    )

    assert response.status_code == 200
    rows = response.json()
    assert rows[0]["period_end"] < rows[-1]["period_end"]
    row = rows[0]
    assert set(row) == {
        "concept", "period_start", "period_end", "value",
        "unit", "form", "accn", "filed", "source", "collected_at",
    }


@needs_db
def test_reading_someone_elses_coverage_is_a_404(api, coverage, other_token):
    theirs = api.get(
        f"/api/coverages/{coverage.id}/financials", headers=auth(other_token)
    )
    missing = api.get("/api/coverages/999999/financials", headers=auth(other_token))

    assert theirs.status_code == 404
    assert theirs.content == missing.content


# --------------------------------------------------------------------------
# Containment - issue #6's third requirement, demonstrated
# --------------------------------------------------------------------------


@needs_db
def test_an_outage_is_a_503_and_not_a_500(api, coverage, owner_token, edgar_is_down):
    """SEC being unreachable is not this application failing."""
    response = api.post(
        f"/api/coverages/{coverage.id}/financials", headers=auth(owner_token)
    )

    assert response.status_code == 503
    assert response.headers["Retry-After"]
    assert set(response.json()) == {"error", "message"}


@needs_db
def test_an_unusable_response_is_a_502_and_not_a_500(
    api, coverage, owner_token, edgar_talks_nonsense
):
    """A broken upstream contract is not retryable, so it is not a 503."""
    response = api.post(
        f"/api/coverages/{coverage.id}/financials", headers=auth(owner_token)
    )

    assert response.status_code == 502
    assert set(response.json()) == {"error", "message"}


@needs_db
def test_an_upstream_failure_tells_the_caller_nothing_about_upstream(
    api, coverage, owner_token, edgar_talks_nonsense
):
    """The body must not name the provider, the field, or the library.

    A 502 body travels into logs, screenshots and bug reports the same way a
    422 does, and the detail belongs in the server log beside the incident.
    """
    response = api.post(
        f"/api/coverages/{coverage.id}/financials", headers=auth(owner_token)
    )

    body = response.text.lower()
    for leak in ("edgar", "sec.gov", "pydantic", "validation error", "units", "decimal"):
        assert leak not in body


@needs_db
def test_an_outage_writes_nothing(
    api, coverage, owner_token, db_session, edgar_is_down
):
    """A failed collection leaves the table as it found it.

    The fetch and the validation both finish before the first row is built, so
    there is no half-written series to clean up - and nothing to explain to a
    user who retries.
    """
    from models import CoverageFinancial

    api.post(f"/api/coverages/{coverage.id}/financials", headers=auth(owner_token))

    assert db_session.query(CoverageFinancial).count() == 0


@needs_db
def test_a_filer_that_reports_nothing_collects_nothing(
    api, coverage, owner_token, monkeypatch
):
    """Every concept 404s. That is a fact about the company, not a failure."""
    body = (FIXTURES / "jpmorgan_revenue_404.xml").read_bytes()
    _install(monkeypatch, lambda request: httpx.Response(404, content=body))

    response = api.post(
        f"/api/coverages/{coverage.id}/financials", headers=auth(owner_token)
    )

    assert response.status_code == 200
    assert response.json()["collected"] == 0
    assert response.json()["concepts"] == []
