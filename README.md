# sweng861-crud-ekk5635

Eungchan Kang · SWENG 861 Software Construction · Penn State

A CRUD API and web UI where each analyst keeps their own company coverage
notes, with financial figures pulled from SEC EDGAR filings. FastAPI and
PostgreSQL behind an Nginx gateway, a Vue 3 front end, and Google OpenID
Connect for login.

## Repository layout

Each week's folder is a copy of the previous week plus that week's work, so a
submitted folder is never changed afterwards. Tags `week-03-submission` and
`week-04-submission` mark the submitted commits. The latest stack is Week 6.

| Folder | Week | Adds | Design notes |
|---|---|---|---|
| `week-01-setup/` | 1 | FastAPI health and hello endpoints | below |
| `week-02-auth/` | 2 | Google OIDC login, session JWT, protected endpoint, rate limiting | [`docs/week-02-auth.md`](docs/week-02-auth.md) |
| `week-03-backend/` | 3 | Coverages CRUD scoped by owner, SEC EDGAR client, Nginx gateway, admin role, one error shape | [`docs/week-03-backend.md`](docs/week-03-backend.md) |
| `week-04-frontend/` | 4 | Vue 3 single-page app: login, list, detail, create and edit | [`docs/week-04-frontend.md`](docs/week-04-frontend.md) |
| `week-05-testing/` | 5 | Unit, integration and component tests with 80% coverage gates | [`week-05-testing/docs/week05-test-report.pdf`](week-05-testing/docs/week05-test-report.pdf) |
| `week-06-devops/` | 6 | CI pipeline, JSON logs under a request ID, Prometheus metrics, Grafana dashboard, SLO alerts and runbooks, front-end image | sections below |

## Run the current stack

Requires Docker and a Google OAuth client whose authorized redirect URI is
`http://localhost:8000/auth/callback`.

```bash
cd week-06-devops/backend
cp .env.example .env          # GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, SESSION_JWT_SECRET, POSTGRES_PASSWORD, SEC_USER_AGENT
docker compose up -d --build  # PostgreSQL, migration, API, front end, gateway, Prometheus, Grafana
curl http://localhost:8000/health   # {"status":"UP","db":"UP"}
```

Open `http://localhost:8000/` and click **Login with Google**. The gateway on
:8000 is the only door:

- `/api`, `/auth`, `/health`, `/docs` and `/openapi.json` go to the API;
- `/metrics` is refused;
- everything else is the single-page app, served by unprivileged Nginx from its own image.

Earlier weeks bind the same ports, so stop their stacks first. Every variable
is documented in `week-06-devops/backend/.env.example`. The front end has no
environment file, so no secret reaches the bundle.

To work on the front end with hot reload, run `npm run dev` in
`week-06-devops/frontend` (:5173, proxying `/api` and `/auth` to :8000). Set
`FRONTEND_URL` on the `api` service in `docker-compose.yml` to
`http://localhost:5173` while you do, so a login returns there instead of to
:8000.

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
| `audit` | `pip-audit`, `npm audit`, and a check for tracked `.env` files ([Security checks](#security-checks-and-secrets)) | a known vulnerability in a dependency, or a committed `.env` |
| `package` | after the three above pass: builds the backend and frontend images as `sweng861-week6-<side>:<commit SHA>` and `:week6`, smoke-tests both, checks neither runs as root and the frontend carries no Node, then scans both with Trivy | the build, the start, a root user, or a scan finding |

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

## Security checks and secrets

### Security checks in CI

Each check runs on every push and pull request, and a failure stops the
images from being built or scanned further.

| Check | Command | Fails when | Deliberately not checked |
|---|---|---|---|
| Backend dependencies | `pip-audit -r requirements.txt` (job `audit`) | any known vulnerability, whatever its severity | — |
| Frontend dependencies | `npm audit --omit=dev --audit-level=high` (job `audit`) | a high or critical advisory in a runtime dependency | dev dependencies; see below |
| Committed `.env` | `git ls-files` (job `audit`) | `.env` or any `.env.*` other than `.env.example` is tracked | — |
| Images | Trivy 0.75.0, `--scanners vuln,secret --severity HIGH,CRITICAL --ignore-unfixed` (job `package`) | a HIGH or CRITICAL vulnerability with a fixed package, or a secret, in either image | findings with no fix published yet |

- **Dev dependencies.** The frontend image holds only the built `dist/`, so dev tooling never runs in production. A full `npm audit --audit-level=high` still runs, report-only. It currently lists `braces` (GHSA-vfj7-8cjw-p6xm, no fixed version yet), which reaches only the ESLint config.
- **Unfixed findings.** A finding with no patched package cannot be fixed by a rebuild. Skipping it keeps the gate actionable, but those risks are visible only in a local scan without `--ignore-unfixed`.
- **Image hardening for the scan.** Both images apply OS security updates at build time. The backend image has no `pip`, and the frontend uses a stable Nginx branch. The `package` job also checks that neither image runs as root.

The first runs of these checks failed on real findings. Screenshots `16` to `19` show them:

- PyJWT 2.13.0, fixed by moving to 2.15.1;
- pip's vendored packages, `libpcre2`, and 42 Alpine packages under the stale `nginx-unprivileged:1.29-alpine` tag.

To reproduce locally:

```bash
pip install pip-audit==2.10.1 && pip-audit -r week-06-devops/backend/requirements.txt
cd week-06-devops/frontend && npm audit --omit=dev --audit-level=high
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:0.75.0 image \
  --scanners vuln,secret --severity HIGH,CRITICAL --ignore-unfixed sweng861-week6-backend:week6
```

### Where secrets live

The secrets are `GOOGLE_CLIENT_SECRET`, `SESSION_JWT_SECRET` and
`POSTGRES_PASSWORD` (inside `DATABASE_URL`). None is in source, in an image, or
in the front-end bundle.

| Environment | Store | How the app receives them |
|---|---|---|
| Local | `week-06-devops/backend/.env`, created from `.env.example`. It is git-ignored, and `.dockerignore` keeps it out of the build context. | `env_file` in `docker-compose.yml`, at container start |
| CI | No secret is needed today. The PostgreSQL service uses throwaway credentials written in `ci.yml`, for a database that exists only for that job. A real credential, such as a registry token, would go in GitHub Actions secrets as `${{ secrets.NAME }}`. | an `env:` entry in the step that needs it |
| Production (not deployed) | A cloud secret manager, such as AWS Secrets Manager. | The container platform injects them as environment variables. The image stays the same in every environment. |

`week-06-devops/backend/tests/test_log_secrets.py` checks that no log line
carries a token, a cookie, an OAuth code, a configured secret or an email.

## Metrics, dashboard and SLOs

`docker compose up` in `week-06-devops/backend` also starts Prometheus and
Grafana. The dashboard is loaded from files at startup; nothing is set up by hand.

| Service | URL | Notes |
|---|---|---|
| Grafana | http://127.0.0.1:3000 | dashboard *SWENG 861 · API*; anonymous read-only, no login form, no basic auth |
| Prometheus | http://127.0.0.1:9090 | scrapes every API replica at `api:8000/metrics` every 15 s; keeps 8 days |

Both ports are bound to loopback only. `/metrics` is served inside the compose
network, and the gateway answers 404 for any path that starts with it.

The API exports these metrics (`week-06-devops/backend/metrics.py`):

| Metric | Labels | Counts |
|---|---|---|
| `http_requests_total` | `method`, `route`, `status` | every request; `route` is the template (`/api/coverages/{coverage_id}`), unmatched paths share `unmatched`, unknown methods share `OTHER` |
| `http_request_duration_seconds` | `method`, `route` | latency histogram, buckets 0.05 to 2.5 s with 0.5 s as an edge |
| `coverages_created_total` | | coverages committed to the database (a 409 duplicate is not counted) |
| `logins_total` | `outcome` | `succeeded`, `client_error` (consent declined, expired cookies, forged state), `service_error` (token exchange or verification failed) |

### SLOs

Each is measured over 7 days. The top row of the dashboard shows the same
expressions over the selected time range, so set the picker to 7 days to read
them as the SLO.

| SLI | SLO | PromQL |
|---|---|---|
| Login success: successful logins over logins that failed for a reason the service owns. A login the caller abandoned or forged is not the service failing. | ≥ 99% | `sum(increase(logins_total{outcome="succeeded"}[7d])) / (sum(increase(logins_total{outcome=~"succeeded\|service_error"}[7d])) + (sum(increase(http_requests_total{route="/auth/callback",status=~"5.."}[7d])) or vector(0)))` |
| API availability: `/api/*` requests that did not end in 5xx | ≥ 99.5% | `1 - (sum(increase(http_requests_total{route=~"/api/.*",status=~"5.."}[7d])) or vector(0)) / sum(increase(http_requests_total{route=~"/api/.*"}[7d]))` |
| Latency: p95 of `GET /api/coverages` | ≤ 500 ms | `histogram_quantile(0.95, sum by (le) (increase(http_request_duration_seconds_bucket{route="/api/coverages",method="GET"}[7d])))` |

`or vector(0)` matters. With no 5xx yet, the 5xx series does not exist and the
whole expression would return no data rather than 100%.

### Using the dashboard in an incident

1. **Check the top row.** It shows which promise is broken: logins, API errors, or latency.
2. **Look at error rate, 4xx against 5xx.** A 5xx rise is the service failing. A 4xx rise alone is usually callers or a scan.
3. **Compare the p95 latency by route.** Latency that climbs before the 5xx points at a slow dependency, either the database or SEC EDGAR.
4. **Check request rate.** A drop to zero with no errors points at the gateway or the network, not the API.
5. **Take a route and a time from the panels to the logs.** Every response carries an `X-Request-ID`, and every API log line is JSON with that `request_id`, so one failing request can be followed end to end (`docker compose logs api | grep <id>`).

Screenshots of the dashboard with data from the running stack are in
`week-06-devops/docs/screenshots/`.

### Alerts

Prometheus evaluates one alert per SLO, from
`week-06-devops/observability/prometheus/rules/slo-alerts.yml`. Each threshold is a
14.4x burn rate of the SLO's error budget: at that rate, a 7-day budget is gone in
about two days.

| Alert | Fires when | For | Severity | Runbook |
|---|---|---|---|---|
| `ApiHighErrorRate` | `/api/*` 5xx over 5 min > 7.2% (0.5% × 14.4), at > 0.1 req/s | 2m | page | [api-high-error-rate](week-06-devops/docs/runbooks/api-high-error-rate.md) |
| `CoveragesLatencyHigh` | `GET /api/coverages` p95 over 5 min > 500 ms | 5m | ticket | [coverages-latency-high](week-06-devops/docs/runbooks/coverages-latency-high.md) |
| `LoginServiceFailures` | server-side login failures over 30 min > 14% (1% × 14.4), with ≥ 5 attempts | 5m | page | [login-service-failures](week-06-devops/docs/runbooks/login-service-failures.md) |

- **Thin traffic.** Each rule has a traffic floor, so one failure out of two requests cannot page.
- **Short windows.** The windows are shorter than a production 1-hour fast-burn window, so the demo stack can show an alert fire within minutes.
- **No Alertmanager.** The stack has no Alertmanager and nowhere to send a page. Alert state is visible at http://127.0.0.1:9090/alerts and in the `ALERTS` series. A deployment would route `severity="page"` to an on-call channel.

`promtool test rules` runs in CI (job `alert-rules`) against
`observability/prometheus/tests/slo-alerts.test.yml`. Every alert is tested two ways:

- **It fires** on a breach, and the test also checks its summary and runbook link.
- **It stays quiet** just under the threshold, on thin traffic, and when the 5xx series does not exist yet.

The same job fails if `prometheus.yml` loads no rule file. A wrong glob would otherwise pass promtool and start Prometheus with no alerts.

**Drill, 2 October 2026.** The steps were:

1. `docker compose stop db` while authenticated `GET /api/coverages` ran at 5 requests a second.
2. `ApiHighErrorRate` went pending 21 s later and fired 2 minutes after that, at an 85% 5xx ratio.
3. After `docker compose start db` it resolved once the 5-minute window had drained.

Screenshots `10` to `13` in `week-06-devops/docs/screenshots/` show the drill:

- the alert firing, with its runbook link;
- the dashboard during the incident;
- the `ALERTS` series going pending, then firing, then gone;
- all three rules inactive afterwards.

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
