"""Routes an administrator may use, and nobody else.

Kept in its own module because the boundary is the point. The assignment asks
for a clear separation between what any authenticated user may do and what an
administrator may do, and a separation stated in the import graph is harder to
erode than one stated in a comment: nothing here is reachable without
require_admin, and nothing in coverages.py can drift into being admin-only
without moving.

The admin view is a separate route rather than a parameter on the tenant one.
A `?all=true` flag would make the ownership filter in list_coverages
conditional, and a filter that is sometimes applied is a filter that will
eventually be skipped by accident - which is the failure #25 tests for. The
tenant list stays unconditionally scoped to the caller; seeing across tenants
means asking a different question at a different URL.

AI use: drafting.
"""

from collections.abc import Sequence

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from db import get_db
from models import Coverage
from schemas import CoverageAdminRead
from security import AuthenticatedUser, require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/coverages", response_model=list[CoverageAdminRead])
def list_all_coverages(
    admin: AuthenticatedUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Sequence[Coverage]:
    """Every coverage in the system, whoever owns it.

    There is no owner_id term in this query, and that is the entire difference
    from the tenant list. It is deliberate here and load-bearing there, which
    is why the two live apart.

    owner_id is returned, unlike everywhere else in the API. A caller who may
    see every row needs to know whose each one is, or the list is a heap of
    rows with no way to act on them; every other response omits the column
    because a tenant only ever sees rows that are already their own.
    """
    return db.scalars(
        select(Coverage).order_by(Coverage.owner_id, Coverage.id)
    ).all()
