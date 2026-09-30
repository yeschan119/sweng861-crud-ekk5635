"""Unit tests for users.py, with no database.

upsert_user is the one place that decides what a returning user is. Its rules
live in a docstring - find by subject, refresh the profile every time, stamp
last_login_at either way - and until now none of them were checked: the
callback tests replace this function with a lambda.

The Session is a stub with the four methods the function calls. That keeps the
test on the rule rather than on the SQL, which is what the integration tests
over a real database are for. The one exception is the lookup itself, where
the statement handed to the session is inspected: "by subject, never by email"
is a claim about the query, so the query is what gets asserted.

Each test is arranged, acted on and asserted in that order.
"""

from datetime import datetime, timezone

import pytest

from models import User
from oidc import GoogleIdentity
from users import upsert_user

SUBJECT = "google-subject-1234567890"


class FakeSession:
    """The four Session methods upsert_user calls, and nothing else.

    Recording rather than mocking: a test can ask what was added, how many
    commits happened and which statement was executed.
    """

    def __init__(self, existing: User | None = None):
        self.existing = existing
        self.added: list[User] = []
        self.commits = 0
        self.refreshed: list[User] = []
        self.statements: list = []

    def scalar(self, statement):
        self.statements.append(statement)
        return self.existing

    def add(self, instance: User) -> None:
        self.added.append(instance)

    def commit(self) -> None:
        self.commits += 1

    def refresh(self, instance: User) -> None:
        self.refreshed.append(instance)


@pytest.fixture
def identity() -> GoogleIdentity:
    """A verified Google identity, as verify_id_token returns one."""
    return GoogleIdentity(subject=SUBJECT, email="student@psu.edu", name="Test Student")


def existing_user(**overrides) -> User:
    """A row this account already has, as a returning login would find it."""
    fields = {
        "id": 7,
        "google_sub": SUBJECT,
        "email": "student@psu.edu",
        "name": "Test Student",
        "last_login_at": datetime(2020, 1, 1, tzinfo=timezone.utc),
    }
    fields.update(overrides)
    return User(**fields)


def test_a_first_login_creates_a_row_keyed_by_the_google_subject(identity):
    session = FakeSession(existing=None)

    user = upsert_user(session, identity)

    assert session.added == [user]
    assert user.google_sub == SUBJECT
    assert user.email == "student@psu.edu"
    assert user.name == "Test Student"


def test_a_returning_login_reuses_the_row_instead_of_adding_a_second(identity):
    already_there = existing_user()
    session = FakeSession(existing=already_there)

    user = upsert_user(session, identity)

    # The same object, and nothing handed to add(): one Google account is one
    # row, which is the whole reason this function exists.
    assert user is already_there
    assert session.added == []


def test_the_row_is_found_by_subject_and_never_by_email(identity):
    session = FakeSession(existing=None)

    upsert_user(session, identity)

    where = str(session.statements[0].whereclause)
    assert "google_sub" in where
    assert "email" not in where


def test_a_changed_profile_is_written_back_on_the_next_login():
    # Google carries the new values; the row still holds last login's.
    stale = existing_user(email="old.address@psu.edu", name="Old Name")
    session = FakeSession(existing=stale)
    renamed = GoogleIdentity(subject=SUBJECT, email="new.address@psu.edu", name="New Name")

    user = upsert_user(session, renamed)

    assert user.email == "new.address@psu.edu"
    assert user.name == "New Name"


def test_last_login_at_is_stamped_even_when_nothing_else_moved(identity):
    unchanged = existing_user()
    session = FakeSession(existing=unchanged)
    before = datetime.now(timezone.utc)

    user = upsert_user(session, identity)

    assert user.last_login_at >= before
    # Timezone-aware, so the value means the same thing wherever it is read.
    assert user.last_login_at.tzinfo is not None


def test_the_row_is_committed_and_refreshed_before_it_is_returned(identity):
    session = FakeSession(existing=None)

    user = upsert_user(session, identity)

    # created_at and updated_at are filled by PostgreSQL, so without the
    # refresh the caller would get a row whose timestamps are still None.
    assert session.commits == 1
    assert session.refreshed == [user]


def test_an_unverified_address_clears_the_one_already_stored():
    """Documents current behaviour, not an intended rule.

    verify_id_token drops the address when Google reports email_verified as
    false, and this function writes that None straight over a value that was
    verified on an earlier login. Recorded in the Week 5 report.
    """
    confirmed = existing_user(email="student@psu.edu")
    session = FakeSession(existing=confirmed)
    unverified = GoogleIdentity(subject=SUBJECT, email=None, name="Test Student")

    user = upsert_user(session, unverified)

    assert user.email is None
