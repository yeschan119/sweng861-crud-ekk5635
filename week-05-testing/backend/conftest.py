"""Test setup shared by every test in this service.

The environment is populated here, before anything imports config, so the
suite never reads the developer's .env and never depends on a real Google
client. Tests that need a token sign one with the key set below.

Most of the suite touches no database. The few tests that do read
TEST_DATABASE_URL from the real environment and skip when it is unset, so a
checkout with no Postgres still runs everything else. It is deliberately a
different database from the one the application uses: the demo rows are what
the screenshots and the Postman collection point at, and a test run that
truncated them would destroy submission evidence.
"""

import json
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

# Read .env before the fake values below are set, so TEST_DATABASE_URL is
# available while DATABASE_URL is still overridden.
load_dotenv()
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

# load_dotenv() does not overwrite variables that already exist, so setting
# these first means .env cannot leak real credentials into a test run.
os.environ.update(
    {
        "GOOGLE_CLIENT_ID": "test-client-id.apps.googleusercontent.com",
        "GOOGLE_CLIENT_SECRET": "test-client-secret",
        "GOOGLE_REDIRECT_URI": "http://localhost:8000/auth/callback",
        "SESSION_JWT_SECRET": "test-signing-key-used-only-by-the-test-suite",
        "SESSION_JWT_TTL_SECONDS": "3600",
        # Never connected to. Nothing in these tests reaches the database.
        "DATABASE_URL": "postgresql+psycopg://unused:unused@localhost:5432/unused",
        # SEC requires a contact address on every request. A test must never
        # send the developer's real one to data.sec.gov.
        "SEC_USER_AGENT": "SWENG861 Test Suite test@example.invalid",
    }
)


@pytest.fixture(scope="session")
def client():
    """A client for the app, which needs no database.

    The protected endpoint reads the caller's identity out of the token and
    touches no table, so these tests prove the gate rather than the
    infrastructure and run in CI with no services started. Since the schema
    moved to Alembic the app has no startup hook either.
    """
    from fastapi.testclient import TestClient

    from main import app

    return TestClient(app)


@pytest.fixture
def valid_token() -> str:
    """A session token exactly as /auth/callback issues one."""
    from models import User
    from tokens import issue_session_token

    # Not persisted: issue_session_token reads only the id and the email.
    return issue_session_token(User(id=7, email="student@psu.edu"))


# ---------------------------------------------------------------------------
# Database fixtures, used only by tests that assert what a constraint does
# ---------------------------------------------------------------------------

needs_db = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not set"
)


def _create_database_if_missing(url: str) -> None:
    """Create the test database when it is not there.

    `docker compose down -v` destroys the volume, and the database that comes
    back holds only what the migrations create - this one is not among them.
    That is a footgun rather than a design: the suite failed with seventeen
    connection errors once for exactly this reason, on a checkout where nothing
    was wrong with the code.

    Creating it here rather than documenting a command means a fresh machine,
    a fresh volume and CI all reach a running suite the same way. The database
    is only ever created; its contents are dropped and rebuilt per session by
    the fixture below.
    """
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.exc import OperationalError

    target = make_url(url)
    probe = create_engine(url)
    try:
        with probe.connect():
            return
    except OperationalError as exc:
        if "does not exist" not in str(exc):
            raise
    finally:
        probe.dispose()

    # AUTOCOMMIT because CREATE DATABASE cannot run inside a transaction.
    admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{target.database}"'))
    finally:
        admin.dispose()


@pytest.fixture(scope="session")
def db_engine():
    """An engine against the test database, with the schema migrated on.

    The schema is created from the models rather than by running Alembic. The
    migrations are verified separately, against the real database, and making
    every test run pay for three revisions would buy nothing here.
    """
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not set")

    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    from models import Base

    _create_database_if_missing(TEST_DATABASE_URL)

    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """A session whose work is rolled back when the test ends.

    Each test therefore starts from an empty table without truncating anything,
    and two tests cannot see each other's rows.

    The session works inside a SAVEPOINT rather than directly on the outer
    transaction. That is not a detail: two handlers roll back deliberately -
    the duplicate-cik insert and the delete that matched no row - and a plain
    session would have aimed those at the transaction this fixture owns,
    discarding the fixture's own rows along with the handler's failed
    statement. A test then watched a correct handler refuse a stranger's
    delete and reported the row as deleted anyway. With create_savepoint the
    handler's rollback stops at its own savepoint, which is what happens in
    production, where the transaction it ends is the request's own.
    """
    from sqlalchemy.orm import Session

    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def coverage(db_session):
    """One user holding one coverage of Tesla, matching the captured fixtures.

    Committed, not flushed. The commit releases the savepoint, which puts these
    rows in the outer transaction - so a handler that rolls back during the
    test cannot take the test's own setup with it. They are still undone at the
    end, when the fixture rolls back that outer transaction.
    """
    from models import Coverage, User

    user = User(google_sub="test-subject", email="analyst@psu.edu")
    db_session.add(user)
    db_session.flush()

    row = Coverage(
        owner_id=user.id, title="Tesla, Inc.", ticker="TSLA", cik="0001318605"
    )
    db_session.add(row)
    db_session.commit()
    return row


@pytest.fixture
def assets_client():
    """A client answering every request with the captured Tesla Assets document."""
    import httpx

    payload = json.loads(
        (Path(__file__).parent / "tests" / "fixtures" / "tesla_assets_200.json").read_text()
    )
    return httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    )


@pytest.fixture
def api(db_session):
    """A TestClient whose requests run inside the test's own transaction.

    get_db is overridden rather than pointed at another database, so a request
    made through this client and an assertion made directly on db_session see
    the same uncommitted rows - and the rollback at the end of the test undoes
    both together.

    Neither commit nor rollback is stubbed out. They used to be, and they no
    longer need to be: the savepoint the session runs in lets a handler end
    its own transaction without touching the one the fixture rolls back. A
    stub would also have made the suite disagree with production about the
    verbs whose whole behaviour is when they commit and when they do not.
    """
    from fastapi.testclient import TestClient

    from db import get_db
    from main import app

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def owner_token(coverage):
    """A session token for the user who owns the coverage fixture."""
    from models import User
    from tokens import issue_session_token

    return issue_session_token(User(id=coverage.owner_id, email="analyst@psu.edu"))


@pytest.fixture
def admin_token(db_session):
    """A token for a user whose row carries the admin role.

    The role is set on the row, not in the token, so this fixture has to write
    to the table - which is the behaviour under test rather than an
    inconvenience: a token cannot make its bearer an administrator.
    """
    from models import User, UserRole
    from tokens import issue_session_token

    boss = User(
        google_sub="test-admin", email="admin@psu.edu", role=UserRole.ADMIN.value
    )
    db_session.add(boss)
    db_session.commit()
    return issue_session_token(boss)


@pytest.fixture
def other_token(db_session):
    """A token for a second user, who owns nothing."""
    from models import User
    from tokens import issue_session_token

    stranger = User(google_sub="test-stranger", email="stranger@psu.edu")
    db_session.add(stranger)
    db_session.commit()
    return issue_session_token(stranger)
