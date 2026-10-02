# sweng861-crud-ekk5635

Eungchan Kang · SWENG 861 Software Construction · Penn State

A CRUD API and web UI where each analyst keeps their own company coverage
notes, with financial figures pulled from SEC EDGAR filings. FastAPI and
PostgreSQL behind an Nginx gateway, a Vue 3 front end, and Google OpenID
Connect for login.

## Repository layout

Each week's folder is a copy of the previous week plus that week's work, so a
submitted folder is never changed afterwards. Tags `week-03-submission` and
`week-04-submission` mark the submitted commits. The latest stack is Week 5.

| Folder | Week | Adds | Design notes |
|---|---|---|---|
| `week-01-setup/` | 1 | FastAPI health and hello endpoints | below |
| `week-02-auth/` | 2 | Google OIDC login, session JWT, protected endpoint, rate limiting | [`docs/week-02-auth.md`](docs/week-02-auth.md) |
| `week-03-backend/` | 3 | Coverages CRUD scoped by owner, SEC EDGAR client, Nginx gateway, admin role, one error shape | [`docs/week-03-backend.md`](docs/week-03-backend.md) |
| `week-04-frontend/` | 4 | Vue 3 single-page app: login, list, detail, create and edit | [`docs/week-04-frontend.md`](docs/week-04-frontend.md) |
| `week-05-testing/` | 5 | Unit, integration and component tests with 80% coverage gates | [`week-05-testing/docs/week05-test-report.pdf`](week-05-testing/docs/week05-test-report.pdf) |

## Run the current stack

Requires Docker, Python 3.10+, Node 22.18+ (or 24.12+), and a Google OAuth client whose
authorized redirect URI is `http://localhost:8000/auth/callback`.

```bash
# API: PostgreSQL, one-shot migration, FastAPI, and the Nginx gateway on :8000
cd week-05-testing/backend
cp .env.example .env          # GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, SESSION_JWT_SECRET, POSTGRES_PASSWORD, SEC_USER_AGENT
docker compose up -d --build
curl http://localhost:8000/health   # {"status":"ok"}

# Front end on :5173, proxying /api and /auth to :8000
cd ../frontend
npm install
npm run dev
```

Open `http://localhost:5173/` and click **Login with Google**. Earlier weeks
bind the same ports, so stop their stacks first. Every variable is documented
in `week-05-testing/backend/.env.example`; the front end has no environment
file, so no secret reaches the bundle.

## Test

One command per side runs everything with coverage and fails below 80%.

```bash
cd week-05-testing/backend
pytest --cov=.              # 96 tests, 94%; needs TEST_DATABASE_URL (a separate test database, created if missing)

cd week-05-testing/frontend
npm run test:coverage       # 103 tests, 99% lines
npm run lint                # oxlint + eslint
npm run type-check
```

Without `TEST_DATABASE_URL` the 47 database-backed tests skip and the backend
gate fails on purpose: a skipped test is not a passed one.

## Continuous integration

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every push and
pull request and tests `week-06-devops/`. Actions is disabled on this
repository by the organization, so the same commits are pushed to a public
mirror, [yeschan119/sweng861-crud-ekk5635](https://github.com/yeschan119/sweng861-crud-ekk5635/actions),
and the runs live there.

| Job | Runs | Fails when |
|---|---|---|
| `backend` | `ruff check .`, then `pytest --cov=.` against a PostgreSQL 17 service container | a lint rule, a test, or coverage under 80% (`.coveragerc`) |
| `frontend` | `npm ci --ignore-scripts`, `npm run lint`, `npm run test:coverage`, `npm run build` | a lint rule, a test, coverage under 80% (`vitest.config.ts`), or a type error |
| `package` | after both pass: builds the backend image as `sweng861-week6-backend:<commit SHA>` and `:week6`, starts it, waits for `/health/live`, checks it does not run as root | the build, the start, or a root user |

The workflow token is read-only and the image is not pushed to a registry.
Each step reproduces locally:

```bash
cd week-06-devops/backend
ruff check . && pytest --cov=.        # needs TEST_DATABASE_URL

cd week-06-devops/frontend
npm ci --ignore-scripts && npm run lint && npm run test:coverage && npm run build

cd week-06-devops
docker build -f backend/Dockerfile -t sweng861-week6-backend:week6 .
```

A green run and two deliberately failing ones (a broken assertion, and the
coverage gate raised to 99%) are in `week-06-devops/docs/screenshots/`.

## Week 1 — Health API

`week-01-setup/backend/`: `GET /health` answers `{"status": "ok"}` and
`GET /api/hello` answers `{"message": "Hello, World!"}`. `/health` sits outside
the `/api` prefix because it is an infrastructure probe, not a feature.

```bash
cd week-01-setup/backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && uvicorn main:app --reload --port 8000
curl -i http://127.0.0.1:8000/health
```

## Week 2 — Authentication

Google OpenID Connect, authorization-code flow with `state`, PKCE (S256) and a
`nonce`. The backend exchanges the code over a back channel, verifies the
`id_token` signature, issuer, audience, expiry and nonce, upserts the user by
Google `sub`, and mints its own HS256 session JWT. `GET /api/hello` is
protected by a `require_auth` dependency: every failure is the same `401`
with `{"error": "Unauthorized", "message": "Valid access token is required"}`.
`/auth/login` and `/auth/callback` allow ten requests per address per minute.

Sixteen tests run with no database and no network:
`cd week-02-auth/backend && .venv/bin/python -m pytest tests/ -v`.
The strategy choice, the OWASP API1/API3/API7 mapping and the rate-limiter
design are in [`docs/week-02-auth.md`](docs/week-02-auth.md).

## Week 3 — CRUD, external data, gateway

`/api/coverages` is a per-analyst resource: `owner_id` comes from the token on
every query and never from the request, so another tenant's row answers `404`
(the same body as an unknown id). Figures come from the SEC EDGAR
`companyconcept` API, which needs a contact `User-Agent` rather than a key.
Nginx is the only published port and spreads requests across API replicas
(`docker compose up --scale api=3`). An admin role, read from the `users`
table rather than the token, unlocks one extra route that answers `403` to
everyone else. Every failure uses one `{"error", "message"}` shape.

Why the list is not public, why `403` and `404` differ, and how the gateway
was made to actually balance are in [`docs/week-03-backend.md`](docs/week-03-backend.md).

## Week 4 — Front end

A Vue 3 + TypeScript single-page app. After Google login the API redirects to
`/login#access_token=…`; the app reads the fragment once, keeps the token in
memory only, and strips it from the URL. One client attaches the bearer token
and maps the API's error shape: a `401` clears the session and returns to
`/login`, a `403` keeps it, a `404` says the item does not exist. Every remote
call goes through `useRequest`, so each page has loading, error-with-retry and
success states; the form validates locally and maps a `422` onto its fields.
Bonus: keyboard-complete, labelled, landmarked accessibility.

Screenshots of every state are in `week-04-frontend/docs/screenshots/`; the
routing, token handling, security checks and layout are described in
[`docs/week-04-frontend.md`](docs/week-04-frontend.md).

## Week 5 — Testing

`week-05-testing/` extends the Week 4 suites: 19 backend unit tests run
`oidc.py` and `users.py` with no database and no network, the integration
tests assert response bodies over an isolated test database, and the front
end has 103 component and module tests. The tests that pin the security model:

| Scenario | Backend (`backend/tests/`) | Frontend (`frontend/src/__tests__/`) |
|---|---|---|
| 401, no or bad token | `test_protected_endpoint.py`: `test_unauthenticated_request_is_rejected`, `test_bad_tokens_are_rejected` | `client.spec.ts` "signs out and throws on 401"; `router.spec.ts` "sends a signed-out user from a protected page to /login" |
| 200, own data | `test_coverages_api.py`: `test_read_returns_the_owners_row`, `test_list_returns_only_the_callers_rows` | `CoveragesView.spec.ts` "lists each coverage with a link to its detail page"; `CoverageDetailView.spec.ts` "asks for the id in the route and shows the coverage" |
| 404, another tenant's row | `test_coverages_api.py`: `test_a_stranger_cannot_reach_another_tenants_row` (GET, PATCH, DELETE), `test_a_refused_delete_leaves_the_row_alone` | `CoverageDetailView.spec.ts` "tells the user when the item does not exist" |
| 403, admin route | `test_admin_authorization.py`: `test_an_ordinary_user_is_refused`, `test_the_refusal_is_403_and_not_the_404_a_tenant_gets` | `client.spec.ts` "keeps the session and throws on 403"; `CoverageDetailView.spec.ts` "tells the user when the item is not theirs to see" |

The test report (structure, coverage, known gaps, AI note) is
`week-05-testing/docs/week05-test-report.pdf`; screenshots of both runs and
both coverage reports are in `week-05-testing/docs/screenshots/`.

## AI use

Claude Code drafted code, tests and documentation one piece at a time in
every week; each piece was reviewed, run and adjusted by the author before the
next. Week 1: the first draft of `main.py`. Week 2: each leg of the login
flow, the auth gate and the tests; the strategy, libraries, PKCE, nonce and
the bonus feature were the author's choices. Week 3: drafting and a review of
the authorization trade-offs. Week 4: the Vue components, API client,
validation module, stylesheet and their specs, checked in the browser against
the running stack. Week 5: the unit tests for `oidc.py` and `users.py` and
the body assertions in the integration tests; one rejected suggestion is
recorded in the test report.
