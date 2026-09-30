"""Put the service into a known state so a demo can be repeated.

Screenshots, the Postman collection and the recorded walkthrough all need
rows to point at, and until now every one of those rows was typed by hand and
deleted again by the next probe. That made a re-take expensive: the evidence
could not be reproduced without rebuilding the data first, and data rebuilt
from memory is not the data the last screenshot showed.

Running this script is the whole setup step. What it leaves behind is fixed:
the same five coverages, owned the same way, carrying the same ids every time.

Two properties are worth the extra lines they cost.

*Identity is reset, not just the rows.* TRUNCATE ... RESTART IDENTITY means
coverage ids start at 1 on every run, so a Postman request saved against
/api/coverages/3 keeps working after a re-seed and a screenshot taken today
matches one taken tomorrow. Deleting rows alone would leave the sequence
advancing and every id would drift.

*Coverages are created through the API, not inserted.* A row written straight
to the table can hold a state the service would refuse - an unknown status, a
second coverage of one filer by one user. Seeding through POST and PATCH means
the demo can only show data the system is actually able to produce. The users
are the exception: nothing but the OIDC callback creates a user, and running
the Google login twice is not something a seed script can do.

The shape of the data is chosen to make the rules visible:

* both analysts cover Apple, which is what the tenancy rule permits and is
  the pair a cross-tenant demo needs - A asking for B's Apple row must 404
  even though A can see an Apple row of their own;
* all three statuses appear, so the status field is not a column of one value;
* every CIK is real and was checked against EDGAR while choosing the external
  API, so the same seed still works once the client in #6 exists.

Run it from this directory, with the database up:

    .venv/bin/python seed_demo.py

AI use: drafting, external API probing and performance checks, and reviewing
security trade-offs.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import text

from config import get_settings
from db import get_session_factory
from main import app
from models import User, UserRole
from tokens import issue_session_token


@dataclass(frozen=True)
class SeededState:
    """What a seeded database contains, by name.

    A positional tuple was returned here until an administrator had to be added
    to it, at which point every caller unpacking four values broke. Naming the
    fields means the next thing the demo needs can be added without touching
    the scripts that only wanted the tokens.
    """

    token_a: str
    token_b: str
    token_admin: str
    ids_a: list[int]
    ids_b: list[int]

# (title, cik, ticker, status). CIKs verified against EDGAR in the #6 probe;
# they are ten characters wide because the leading zeros are part of the key.
ANALYST_A = [
    ("Apple Inc.", "0000320193", "AAPL", "active"),
    ("Microsoft Corporation", "0000789019", "MSFT", "draft"),
    ("JPMorgan Chase & Co.", "0000019617", "JPM", "archived"),
]
ANALYST_B = [
    # Same filer as A's first row, deliberately: one filer may be covered by
    # each of two analysts, and this pair is what a cross-tenant demo needs.
    ("Apple Inc.", "0000320193", "AAPL", "active"),
    ("Tesla, Inc.", "0001318605", "TSLA", "draft"),
]


def reset(session) -> None:
    """Empty both tables and restart their id sequences.

    CASCADE is required rather than optional: coverages carry a foreign key to
    users, so users cannot be truncated on its own. Both tables are named
    anyway, because RESTART IDENTITY only resets the sequences of the tables
    it is given and a coverage id that kept climbing would defeat the point.
    """
    session.execute(text("TRUNCATE coverages, users RESTART IDENTITY CASCADE"))
    session.commit()


def create_users(session) -> tuple[User, User, User]:
    """Insert the two analysts and the administrator the demo needs.

    Written directly to the table because there is no other way in: a user row
    is created by the OIDC callback after Google authenticates someone, and a
    script cannot drive that. The google_sub values are obviously synthetic so
    that a real login is never confused with a seeded account.

    The administrator holds no coverages of their own. That is the point of the
    account rather than an omission: every row the admin route returns belongs
    to somebody else, so a demo cannot mistake "sees all rows" for "sees their
    own". Their tenant list is empty while their admin list is not.

    role is set here because it is a column, not a token claim - which is
    exactly what the Postman demo shows. No token can grant it.
    """
    a = User(google_sub="seed-analyst-a", email="analyst-a@psu.edu", name="Analyst A")
    b = User(google_sub="seed-analyst-b", email="analyst-b@psu.edu", name="Analyst B")
    admin = User(
        google_sub="seed-admin",
        email="admin@psu.edu",
        name="Administrator",
        role=UserRole.ADMIN.value,
    )
    session.add_all([a, b, admin])
    session.commit()
    return a, b, admin


def create_coverages(client: TestClient, token: str, rows: list[tuple]) -> list[int]:
    """Create one analyst's coverages over HTTP and return the new ids.

    status is not sent to POST. The column defaults to 'draft' in the schema
    and the create endpoint does not accept the field, so a row that should end
    up somewhere else gets there by the same PATCH a user would send. Seeding a
    status the API cannot set would demonstrate a transition that does not
    exist.
    """
    headers = {"Authorization": f"Bearer {token}"}
    ids = []
    for title, cik, ticker, status in rows:
        created = client.post(
            "/api/coverages",
            json={"title": title, "cik": cik, "ticker": ticker},
            headers=headers,
        )
        created.raise_for_status()
        coverage_id = created.json()["id"]
        if status != "draft":
            moved = client.patch(
                f"/api/coverages/{coverage_id}",
                json={"status": status},
                headers=headers,
            )
            moved.raise_for_status()
        ids.append(coverage_id)
    return ids


def seed() -> SeededState:
    """Reset and repopulate, returning the tokens and ids but printing nothing.

    Split from main so that another script can put the database into this state
    without the report below landing in its output. demo_walkthrough.py is the
    caller that needs this: its transcript is screenshotted and submitted, and
    the report prints bearer tokens.
    """
    session = get_session_factory()()
    try:
        reset(session)
        analyst_a, analyst_b, administrator = create_users(session)
        token_a = issue_session_token(analyst_a)
        token_b = issue_session_token(analyst_b)
        token_admin = issue_session_token(administrator)
    finally:
        session.close()

    client = TestClient(app)
    ids_a = create_coverages(client, token_a, ANALYST_A)
    ids_b = create_coverages(client, token_b, ANALYST_B)
    return SeededState(token_a, token_b, token_admin, ids_a, ids_b)


def main() -> None:
    state = seed()
    ids_a, ids_b = state.ids_a, state.ids_b

    ttl = get_settings().session_jwt_ttl_seconds
    expires = datetime.now(timezone.utc).timestamp() + ttl

    print("seeded\n")
    for label, rows, ids in (("A", ANALYST_A, ids_a), ("B", ANALYST_B, ids_b)):
        print(f"  analyst {label}")
        for (title, cik, ticker, status), coverage_id in zip(rows, ids):
            print(f"    id={coverage_id:<3} {status:<9} {ticker:<5} {cik}  {title}")
    print()
    print(f"  cross-tenant demo: analyst A asking for id={ids_b[0]} must answer 404,")
    print(f"  though A holds the same filer at id={ids_a[0]}.")
    print()
    print("  role demo: analyst A gets 403 from /api/admin/coverages; the admin")
    print(f"  gets 200 and all {len(ids_a) + len(ids_b)} rows, while their own list is empty.")
    print()
    # Printed rather than written to a file: a bearer token belongs in a
    # terminal a person is looking at, not in a file that can be committed.
    print(f"  token A:     {state.token_a}")
    print(f"  token B:     {state.token_b}")
    print(f"  token admin: {state.token_admin}")
    print()
    print(
        f"  all three expire in {ttl // 60} min, at "
        f"{datetime.fromtimestamp(expires, timezone.utc).strftime('%H:%M:%SZ')}"
        " - re-run this script for a fresh set."
    )


if __name__ == "__main__":
    main()
