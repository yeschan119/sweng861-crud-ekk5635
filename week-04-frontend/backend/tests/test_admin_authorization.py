"""The admin boundary: who may see across tenants, and who is told no.

Assignment 4-6 asks for an admin role that can manage all data, and for a clear
line between what any authenticated user may do and what an administrator may.
This file tests the line, in both directions - that an administrator crosses it
and that an ordinary user does not.

The 403 here and the 404 in test_coverages_api.py are deliberately different
answers, and the difference is the subject of one of the tests below.

AI use: drafting and test-case enumeration.
"""

import pytest

from conftest import needs_db

ADMIN_PATH = "/api/admin/coverages"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@needs_db
def test_an_ordinary_user_is_refused(api, owner_token):
    """The role is the only thing between this caller and the route."""
    response = api.get(ADMIN_PATH, headers=auth(owner_token))

    assert response.status_code == 403
    assert response.json()["error"] == "Forbidden"


@needs_db
def test_the_refusal_is_403_and_not_the_404_a_tenant_gets(api, coverage, owner_token):
    """Two refusals that hide different things.

    A cross-tenant request answers 404 because the existence of a row is the
    secret. The admin route keeps no such secret: it is one fixed path, the
    same for every caller, and it is published in the OpenAPI document. 404
    there would tell an administrator who had just lost the role that the
    feature was gone.
    """
    admin_route = api.get(ADMIN_PATH, headers=auth(owner_token))
    someone_elses_row = api.get("/api/coverages/99999", headers=auth(owner_token))

    assert admin_route.status_code == 403
    assert someone_elses_row.status_code == 404


@needs_db
def test_an_admin_sees_every_tenants_rows(api, coverage, admin_token):
    """The one query in the service with no owner_id term."""
    response = api.get(ADMIN_PATH, headers=auth(admin_token))

    assert response.status_code == 200
    # The coverage fixture belongs to someone else entirely.
    assert coverage.id in [row["id"] for row in response.json()]


@needs_db
def test_an_admin_is_told_who_owns_each_row(api, coverage, admin_token):
    """owner_id is published here and nowhere else.

    A list of every row with no owner on it cannot be acted on, which is why
    this response model exists at all.
    """
    rows = api.get(ADMIN_PATH, headers=auth(admin_token)).json()

    assert all("owner_id" in row for row in rows)


@needs_db
def test_the_tenant_list_is_unaffected_by_the_admin_route(api, coverage, admin_token):
    """An administrator's own list is still only their own.

    The admin view is a separate route, not a mode the ordinary one slips into.
    If seeing across tenants were a flag on list_coverages, this is where the
    leak would show.
    """
    response = api.get("/api/coverages", headers=auth(admin_token))

    assert response.status_code == 200
    assert response.json() == []


@needs_db
def test_the_admin_route_still_needs_a_token(api):
    """require_admin is layered on require_auth, so the 401 comes first."""
    response = api.get(ADMIN_PATH)

    assert response.status_code == 401


@needs_db
def test_a_token_cannot_promote_its_bearer(api, db_session, owner_token):
    """The role is read from the row at request time, not from the token.

    The same token is refused and then accepted, with nothing changed but the
    column. That is the whole argument for keeping the role out of the token:
    a grant takes effect on the next request rather than the next login, and
    so does its removal.
    """
    from models import User

    assert api.get(ADMIN_PATH, headers=auth(owner_token)).status_code == 403

    db_session.query(User).filter(User.email == "analyst@psu.edu").update(
        {"role": "admin"}
    )
    db_session.commit()

    assert api.get(ADMIN_PATH, headers=auth(owner_token)).status_code == 200
