"""Collecting external figures for a coverage, and reading them back.

A sub-resource of coverages, and scoped the same way. The id in the path names
the parent, which is where this rule is easiest to lose: it is tempting to
fetch the child rows by coverage_id and be done, and that query would answer
with another tenant's figures for anyone who guessed an id. The coverage is
therefore resolved first, by owner, and the rows are read through it.

Nothing here catches an EDGAR failure. The client raises one of three typed
errors and errors.py turns each into a status code, so an endpoint added later
inherits that behaviour by existing rather than by remembering to.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from db import get_db
from edgar_collection import collect_coverage
from models import Coverage, CoverageFinancial
from schemas import CoverageFinancialRead, CollectionReport
from security import AuthenticatedUser, require_auth

router = APIRouter(prefix="/api/coverages/{coverage_id}/financials", tags=["financials"])


def _own_coverage(db: Session, coverage_id: int, user: AuthenticatedUser) -> Coverage:
    """The caller's coverage, or the same 404 the coverages API answers with.

    Ownership is a term in the WHERE clause rather than a check afterwards, and
    a coverage belonging to someone else is indistinguishable from one that
    does not exist - answering 403 would confirm the row exists and turn a loop
    over ids into a census of other tenants.
    """
    coverage = db.scalars(
        select(Coverage).where(
            Coverage.id == coverage_id,
            Coverage.owner_id == user.id,
        )
    ).one_or_none()

    if coverage is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Coverage not found",
        )
    return coverage


@router.post("", response_model=CollectionReport)
def collect_financials(
    coverage_id: int,
    user: AuthenticatedUser = Depends(require_auth),
    db: Session = Depends(get_db),
) -> CollectionReport:
    """Fetch this filer's figures from the external source and store them.

    POST rather than GET: this reaches out to another system and changes rows
    here, so it is not something a cache, a prefetch or a crawler should be
    free to repeat. It is not PUT either - the caller supplies no
    representation, and what gets written is whatever the filer has reported by
    now.

    Repeating it is safe. Each row is written by period, and a re-collection
    updates in place rather than adding a second series.
    """
    coverage = _own_coverage(db, coverage_id, user)

    collected = collect_coverage(db, coverage)
    db.commit()

    return CollectionReport(
        coverage_id=coverage.id,
        collected=sum(collected.values()),
        concepts=sorted(collected),
    )


@router.get("", response_model=list[CoverageFinancialRead])
def list_financials(
    coverage_id: int,
    user: AuthenticatedUser = Depends(require_auth),
    db: Session = Depends(get_db),
) -> list[CoverageFinancial]:
    """The figures stored for this coverage, oldest first within each concept.

    Ordered rather than left to the database: a caller plotting a series, and a
    screenshot of this response, both read as a time line only if the rows
    arrive in one.
    """
    coverage = _own_coverage(db, coverage_id, user)

    return list(
        db.scalars(
            select(CoverageFinancial)
            .where(CoverageFinancial.coverage_id == coverage.id)
            .order_by(CoverageFinancial.concept, CoverageFinancial.period_end)
        )
    )
