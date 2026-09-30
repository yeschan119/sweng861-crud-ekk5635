"""The shape EDGAR promises, checked before anything is read out of it.

The client in edgar.py decides whether a response arrived. This module decides
whether what arrived is the document it claims to be. Keeping the two apart is
what lets the transport be tested against a dead host and the contract be
tested against a captured body, with no network in either case.

Only structure is settled here. Whether a particular figure is worth storing -
current enough, from a form worth trusting - is a separate judgement that runs
after this one, because a stale value is a well-formed document.

Three fields carry the whole reason this module exists, and each was measured
against the live API rather than read off the documentation.

``start`` is optional, and not at random. A concept is either an instant or a
duration: Assets and StockholdersEquity are balances at a moment and carry no
start date at all, while NetIncomeLoss and revenue cover a period and always
carry one. Apple reports 0 of 146 Assets facts with a start and 338 of 338 for
NetIncomeLoss. Requiring the field would therefore reject every balance-sheet
figure this application collects - half of the four concepts - while the two
income-statement ones passed, which is the kind of gap that looks like an
upstream outage rather than a schema mistake.

``fy`` and ``fp`` are optional for a related reason: they name a fiscal year
and period, and not every filing is made for one. Both are null on 8-K current
reports and on proxy statements, and never null on 10-K, 10-Q or their
amendments. The keys are always present, so a check that only asked whether
the field existed would call them mandatory and then reject live documents.

``frame`` is optional too. It is EDGAR's own label for a comparable calendar
period and is absent whenever a filer's fiscal period does not line up with
one, so it is useful when present and never something to depend on.

``units`` is asserted rather than assumed. Every response measured carried
exactly one key, ``USD``. A filer reporting in another currency would otherwise
have its figures stored beside dollar amounts with nothing marking the
difference, so anything but a single USD block is refused here.

Unknown fields are ignored, which is the opposite of the rule in schemas.py.
That asymmetry is deliberate: this application owns its own API, so a client
sending an unexpected key is making a mistake worth reporting, but it does not
own EDGAR, and the SEC adding a field to its documents is not an event that
should stop collection.

AI use: drafted with Claude from a measured sample of twelve live responses.
"""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from edgar import EdgarError

# The only unit block this application stores. See the module docstring.
EXPECTED_UNIT = "USD"


class EdgarValidationError(EdgarError):
    """A response that parsed as JSON but is not the document it claims to be.

    Subclasses EdgarError so that a caller which treats "EDGAR did not work" as
    one case still catches it, while a caller that separates an outage worth
    retrying from a contract that has changed can tell the two apart. Retrying
    this one would produce the same document.
    """


class EdgarFact(BaseModel):
    """One reported figure, as it appears inside a unit block."""

    model_config = ConfigDict(extra="ignore")

    # Present on every fact measured.
    end: date
    # Decimal rather than float: these are money, and the largest values run to
    # twelve digits. Binary floating point has no exact representation for most
    # decimal fractions, and a figure that is off in its last place is worse
    # than one that is missing, because nothing about it looks wrong.
    val: Decimal
    # The accession number of the filing this figure came from. It is what
    # makes a stored row traceable back to a document on EDGAR.
    accn: str = Field(min_length=1)
    form: str = Field(min_length=1, max_length=16)
    filed: date

    # Null on filings that are not made for a fiscal period. Measured across
    # 3,125 facts from four filers: never null on 10-K, 10-Q or their
    # amendments, and null on 57% of 8-K facts and on every proxy statement
    # (DEF 14A, PRE 14A). The key is always present - it is the value that is
    # null - so requiring the field passed a shape check and still rejected
    # live documents from Apple and Microsoft.
    fy: int | None = None
    fp: str | None = Field(default=None, max_length=4)

    # Absent on instant concepts - Assets, StockholdersEquity. Present on every
    # duration concept. See the module docstring.
    start: date | None = None
    # EDGAR's comparable-period label, absent when the fiscal period does not
    # align with a calendar one.
    frame: str | None = None

    @model_validator(mode="after")
    def _period_is_ordered(self) -> "EdgarFact":
        """A duration cannot end before it starts.

        Cheap, and it catches the one internal contradiction this structure can
        express. A fact whose period runs backwards would otherwise be stored
        and then quietly break any later comparison that sorts on end date.
        """
        if self.start is not None and self.start > self.end:
            raise ValueError(f"period ends {self.end} before it starts {self.start}")
        return self


class CompanyConcept(BaseModel):
    """The envelope: one accounting concept, for one filer, with its facts."""

    model_config = ConfigDict(extra="ignore")

    cik: int
    taxonomy: str = Field(min_length=1)
    tag: str = Field(min_length=1)
    label: str | None = None
    entity_name: str | None = Field(default=None, alias="entityName")
    units: dict[str, list[EdgarFact]]

    @model_validator(mode="after")
    def _exactly_one_usd_block(self) -> "CompanyConcept":
        """Refuse anything but a single USD block.

        Not a guess about what else EDGAR might send: every response measured
        carried exactly one key. Accepting a second currency would put figures
        of two denominations in the same column with nothing to tell them
        apart, and picking one silently would be worse than refusing.
        """
        keys = set(self.units)
        if keys != {EXPECTED_UNIT}:
            raise ValueError(
                f"expected a single {EXPECTED_UNIT} unit block, got {sorted(keys)}"
            )
        return self

    @property
    def facts(self) -> list[EdgarFact]:
        """The USD facts, which the validator above has already guaranteed."""
        return self.units[EXPECTED_UNIT]

    @property
    def padded_cik(self) -> str:
        """The CIK as coverages stores it: ten digits, zero-padded.

        EDGAR sends this as an integer - 320193, not "0000320193" - while the
        coverages column is CHAR(10). Converting here means the comparison that
        proves a response belongs to the coverage that asked for it is made on
        one representation rather than two.
        """
        return str(self.cik).zfill(10)


def parse_company_concept(payload: object) -> CompanyConcept:
    """Validate a decoded companyconcept document.

    Raises ``EdgarValidationError`` and nothing else. Pydantic's own
    ValidationError is deliberately not allowed out: callers of this package
    already handle EdgarError, and letting a second exception type escape would
    mean a malformed document reaches the unhandled-error handler and answers a
    caller with a 500 - the outcome the client was built to prevent.

    The original message is kept because it names the failing field and the
    reason, and it is logged rather than returned to any client.
    """
    try:
        return CompanyConcept.model_validate(payload)
    except ValidationError as exc:
        raise EdgarValidationError(f"EDGAR document failed validation: {exc}") from exc
