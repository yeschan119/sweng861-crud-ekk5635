"""The five CRUD endpoints, and the tenancy rule they are all scoped by.

Nothing here tested the coverages API until now. #7 brought the suite from 11
tests to 38, but every one of those additions landed on the authentication gate
or the EDGAR path - the surface worth 50 points had no automated coverage at
all, and the only evidence it worked was a screenshot of a terminal.

Two decisions shape the file.

*The assertions are made on HTTP, not on the session.* Each test sends a real
request through the `api` fixture and reads the status and the body back. A
test that called the handler directly, or checked the table afterwards, would
still pass if the router stopped being mounted or the response model started
leaking owner_id - the things a caller would actually notice.

*A cross-tenant test compares two responses rather than checking one.* The rule
#10 settled is not "someone else's row answers 404"; it is that someone else's
row is **indistinguishable** from one that never existed. A test asserting only
the status code would pass against a handler that answered 404 with "not
yours", which tells a caller looping over ids exactly which ones are real. So
the stranger's 404 is compared byte for byte with the 404 for an id nobody
owns.

AI use: drafting and test-case enumeration.
"""

import pytest

from conftest import needs_db

# An id no fixture creates, so a request for it is a genuine miss. Compared
# against the stranger's 404 to prove the two are the same answer.
MISSING_ID = 99_999

APPLE = {"title": "Apple Inc.", "ticker": "AAPL", "cik": "0000320193"}


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def rejected_fields(response) -> list[str]:
    """The fields a 422 names, e.g. ["body.cik"].

    Only the field list is read back. The wording beside it is pydantic's and
    moves between releases; which field was refused is this service's own
    contract and is what these tests are about.
    """
    return [entry["field"] for entry in response.json()["details"]]


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@needs_db
def test_create_returns_201_and_the_stored_row(api, owner_token):
    response = api.post("/api/coverages", json=APPLE, headers=auth(owner_token))

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Apple Inc."
    assert body["cik"] == "0000320193"
    # Not supplied by the caller: the column default is what sets it.
    assert body["status"] == "draft"


@needs_db
def test_create_logs_the_new_id_under_the_request_id(api, owner_token, json_logs):
    import json

    response = api.post(
        "/api/coverages", json=APPLE, headers={**auth(owner_token), "X-Request-ID": "trace-c1"}
    )

    entries = [json.loads(line) for line in json_logs]
    [created] = [e for e in entries if e.get("event") == "coverage_created"]
    [request] = [e for e in entries if e.get("event") == "request"]
    assert created["coverage_id"] == response.json()["id"]
    assert created["request_id"] == request["request_id"] == "trace-c1"


@needs_db
def test_create_increments_the_coverages_created_counter(api, owner_token):
    from prometheus_client import REGISTRY

    before = REGISTRY.get_sample_value("coverages_created_total")

    api.post("/api/coverages", json=APPLE, headers=auth(owner_token))
    api.post("/api/coverages", json=APPLE, headers=auth(owner_token))  # 409, not counted

    assert REGISTRY.get_sample_value("coverages_created_total") == before + 1


@needs_db
def test_create_never_returns_owner_id(api, owner_token):
    """The response model has no owner_id, and that is worth pinning.

    Adding the column to CoverageRead would be a one-line change that no other
    test would notice, and it would publish one tenant's user id to another.
    """
    response = api.post("/api/coverages", json=APPLE, headers=auth(owner_token))

    assert "owner_id" not in response.json()


@needs_db
def test_create_rejects_a_caller_supplied_owner_id(api, owner_token, other_token):
    """`extra="forbid"` is the reason a client cannot choose its own landlord.

    Without it pydantic would drop the unknown key and answer 201, and the
    caller would believe they had created a row for someone else.
    """
    response = api.post(
        "/api/coverages",
        json={**APPLE, "owner_id": 1},
        headers=auth(owner_token),
    )

    assert response.status_code == 422
    # The envelope every failure in this service shares, asserted once here.
    assert response.json()["error"] == "Unprocessable Content"
    assert rejected_fields(response) == ["body.owner_id"]


@needs_db
def test_create_rejects_a_second_coverage_of_the_same_filer(api, owner_token, coverage):
    """The 409 comes from the constraint, not from a lookup before the insert."""
    response = api.post(
        "/api/coverages",
        json={"title": "Tesla again", "cik": coverage.cik},
        headers=auth(owner_token),
    )

    assert response.status_code == 409
    # The contract derives `error` from the status code, so it is the reason
    # phrase rather than a slug a handler chose - that is what makes it unable
    # to drift away from the code beside it.
    assert response.json()["error"] == "Conflict"


@needs_db
def test_two_users_may_cover_the_same_filer(api, coverage, other_token):
    """The unique constraint is (owner_id, cik), and this is the difference.

    A constraint on cik alone would let whoever registered a filer first stop
    every other tenant from following it.
    """
    response = api.post(
        "/api/coverages",
        json={"title": "Tesla, Inc.", "cik": coverage.cik},
        headers=auth(other_token),
    )

    assert response.status_code == 201
    body = response.json()
    # A second row for the same filer, not a view of the first tenant's.
    assert body["cik"] == coverage.cik
    assert body["id"] != coverage.id


# ---------------------------------------------------------------------------
# Read and list
# ---------------------------------------------------------------------------


@needs_db
def test_read_returns_the_owners_row(api, coverage, owner_token):
    response = api.get(f"/api/coverages/{coverage.id}", headers=auth(owner_token))

    assert response.status_code == 200
    assert response.json()["id"] == coverage.id


@needs_db
def test_a_created_row_comes_back_on_a_later_get(api, owner_token):
    """The one test that crosses two requests, which is the point of it.

    Create and read each pass through their own response model; this is the
    only test that asserts the two agree. It does not prove persistence -
    the api fixture shares one session between both requests.
    """
    created = api.post("/api/coverages", json=APPLE, headers=auth(owner_token))
    assert created.status_code == 201

    fetched = api.get(
        f"/api/coverages/{created.json()['id']}", headers=auth(owner_token)
    )

    assert fetched.status_code == 200
    assert fetched.json() == created.json()
    # The tenant column stays server-side on the way back out too.
    assert "owner_id" not in fetched.json()


@needs_db
def test_list_returns_only_the_callers_rows(api, coverage, owner_token):
    api.post("/api/coverages", json=APPLE, headers=auth(owner_token))

    body = api.get("/api/coverages", headers=auth(owner_token)).json()

    assert {row["cik"] for row in body} == {coverage.cik, APPLE["cik"]}


@needs_db
def test_a_strangers_list_is_empty(api, coverage, other_token):
    """The row exists; it is simply not this caller's."""
    response = api.get("/api/coverages", headers=auth(other_token))

    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


@needs_db
def test_patch_changes_only_the_fields_sent(api, coverage, owner_token):
    response = api.patch(
        f"/api/coverages/{coverage.id}",
        json={"status": "active"},
        headers=auth(owner_token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "active"
    # Absent from the request, so it must survive untouched.
    assert body["title"] == coverage.title


@needs_db
def test_patch_refuses_to_replace_the_filer(api, coverage, owner_token):
    """cik is not a field on CoverageUpdate, so naming it is a 422.

    The external rows from #7 key off cik. Letting it change would repoint
    figures that were collected for a different company.
    """
    response = api.patch(
        f"/api/coverages/{coverage.id}",
        json={"cik": "0000320193"},
        headers=auth(owner_token),
    )

    assert response.status_code == 422
    assert rejected_fields(response) == ["body.cik"]


@needs_db
def test_patch_refuses_an_explicit_null_on_a_required_column(api, coverage, owner_token):
    """Omitting a key means "leave it"; sending null means "clear it".

    title is NOT NULL, so the second has to be refused at the schema. #11 found
    this by testing it against description, which was nullable anyway and
    proved nothing - audit finding 5.
    """
    response = api.patch(
        f"/api/coverages/{coverage.id}",
        json={"title": None},
        headers=auth(owner_token),
    )

    assert response.status_code == 422
    assert rejected_fields(response) == ["body.title"]
    # This wording is our own validator's, not pydantic's, so it is pinned.
    assert response.json()["details"][0]["message"] == (
        "Value error, title cannot be null"
    )


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@needs_db
def test_delete_returns_204_and_the_row_is_gone(api, coverage, owner_token):
    assert api.delete(
        f"/api/coverages/{coverage.id}", headers=auth(owner_token)
    ).status_code == 204

    assert api.get(
        f"/api/coverages/{coverage.id}", headers=auth(owner_token)
    ).status_code == 404


# ---------------------------------------------------------------------------
# Cross-tenant access - the cases Week 5 grades
# ---------------------------------------------------------------------------


@needs_db
@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_a_stranger_cannot_reach_another_tenants_row(
    api, coverage, other_token, method
):
    """And the refusal is the same one an unknown id gets, byte for byte.

    Comparing the two bodies is the point. Asserting 404 alone would still pass
    if the handler distinguished the cases in its message, and that difference
    is all an attacker needs to enumerate which ids exist.
    """
    kwargs = {"json": {"title": "seized"}} if method == "patch" else {}

    theirs = getattr(api, method)(
        f"/api/coverages/{coverage.id}", headers=auth(other_token), **kwargs
    )
    nobodys = getattr(api, method)(
        f"/api/coverages/{MISSING_ID}", headers=auth(other_token), **kwargs
    )

    assert theirs.status_code == 404
    assert theirs.json() == nobodys.json()
    # Equality alone would also hold if both answered with nothing, so the
    # body the two share is pinned as well.
    assert theirs.json() == {"error": "Not Found", "message": "Coverage not found"}


@needs_db
def test_a_refused_delete_leaves_the_row_alone(api, coverage, other_token, owner_token):
    """The status code is not the assertion that matters here.

    A handler that deleted the row and then answered 404 would satisfy every
    check above. What proves the row survived is its owner still reading it.
    """
    api.delete(f"/api/coverages/{coverage.id}", headers=auth(other_token))

    assert api.get(
        f"/api/coverages/{coverage.id}", headers=auth(owner_token)
    ).status_code == 200


@needs_db
def test_a_refused_patch_leaves_the_row_alone(api, coverage, other_token, owner_token):
    api.patch(
        f"/api/coverages/{coverage.id}",
        json={"title": "seized"},
        headers=auth(other_token),
    )

    body = api.get(f"/api/coverages/{coverage.id}", headers=auth(owner_token)).json()
    assert body["title"] == coverage.title


# ---------------------------------------------------------------------------
# Unauthenticated
# ---------------------------------------------------------------------------


@needs_db
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/coverages"),
        ("get", "/api/coverages"),
        ("get", "/api/coverages/1"),
        ("patch", "/api/coverages/1"),
        ("delete", "/api/coverages/1"),
    ],
)
def test_every_endpoint_requires_a_token(api, method, path):
    """All five, not a sample.

    A router gains endpoints one at a time, and the one added without a
    dependency is the one no sampled test covers.
    """
    # Only the verbs that carry a body get one. TestClient.get and .delete
    # take no `json` argument at all, and passing one is a TypeError rather
    # than a request the gate ever sees.
    kwargs = {"json": {}} if method in ("post", "patch") else {}
    response = getattr(api, method)(path, **kwargs)

    assert response.status_code == 401
    # One body for all five: a verb that answered differently would leak
    # which paths exist to a caller with no token.
    assert response.json() == {
        "error": "Unauthorized",
        "message": "Valid access token is required",
    }
