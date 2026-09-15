"""Request and response bodies for the coverages API.

owner_id appears in neither direction. It is not accepted on the way in, so a
client cannot choose it, and it is not returned, because every row a caller can
read is already their own.
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from models import CoverageStatus


class CoverageCreate(BaseModel):
    # Unknown fields are rejected rather than dropped. A client that sends
    # owner_id is told its request was wrong instead of believing it worked.
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    status: CoverageStatus = CoverageStatus.DRAFT
    ticker: str | None = Field(default=None, max_length=10)
    # Exactly ten digits, zero-padded: 320193 and 0000320193 are the same
    # filer, and only the padded form matches the EDGAR path.
    cik: str = Field(pattern=r"^\d{10}$")


class CoverageUpdate(BaseModel):
    """A partial update. Absent keys are left alone; cik is not accepted.

    cik is missing here rather than optional. A coverage is identified by the
    filer it follows, and the external rows from #7 key off it, so changing it
    would silently repoint or orphan them. Changing which company you cover
    means deleting the coverage and creating another.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: CoverageStatus | None = None
    ticker: str | None = Field(default=None, max_length=10)

    @field_validator("title", "status")
    @classmethod
    def _not_explicitly_null(cls, value: object, info) -> object:
        # Omitting a key means "leave it"; sending null means "clear it". These
        # two columns are NOT NULL, so null has to be refused here rather than
        # reaching the database as an integrity error.
        if value is None:
            raise ValueError(f"{info.field_name} cannot be null")
        return value


class CoverageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    status: CoverageStatus
    ticker: str | None
    cik: str
    created_at: datetime
    updated_at: datetime


class CoverageAdminRead(CoverageRead):
    """A coverage as an administrator sees it: the same row, plus its owner.

    Extending CoverageRead rather than restating its fields means the two
    cannot drift - a column added to the tenant view appears here too, which is
    the direction that matters. The only addition is owner_id, and it is the
    reason a separate model exists at all: an administrator looking at every
    row needs to know whose each one is, and no tenant-facing response says.
    """

    owner_id: int


class CollectionReport(BaseModel):
    """What one collection run did, in the terms the caller asked in.

    A count and the tags it came from, not the rows themselves. The rows are a
    GET away, and returning sixty of them from a POST would make the response
    grow with the filer's history for no reason the caller stated.
    """

    coverage_id: int
    collected: int
    # Sorted so two runs that collected the same things read the same, and the
    # tag is the one actually stored - which matters for revenue, where a
    # fallback decides between two.
    concepts: list[str]


class CoverageFinancialRead(BaseModel):
    """One stored figure.

    coverage_id is absent for the same reason owner_id is absent from
    CoverageRead: the caller asked for this coverage's figures by naming it in
    the path, and echoing the id back tells them nothing they did not send.

    The internal row id is absent too. Nothing addresses one of these
    individually - they are collected and read as a series - so publishing an
    id would invite a URL that does not exist.
    """

    model_config = ConfigDict(from_attributes=True)

    concept: str
    period_start: date | None
    period_end: date
    value: Decimal
    unit: str
    form: str
    accn: str
    filed: date
    source: str
    collected_at: datetime
