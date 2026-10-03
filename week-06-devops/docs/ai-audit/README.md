# AI first drafts

Each `.draft` file is an AI assistant's first output, saved unchanged before any review or fix.
The reviewed version lives at the path in the table; compare the two with `diff -u <draft> <final>`.

| Draft | Final | Date | Request |
|---|---|---|---|
| `health.py.draft` | `backend/health.py` (+ `get_probe_engine` in `backend/db.py`) | 2026-09-30 | Issue #80: `/health` and `/health/ready` report the database (200 UP / 503 DOWN), `/health/live` checks only the process |
| `Dockerfile.draft` | `backend/Dockerfile` | 2026-09-30 | Issue #80: point the HEALTHCHECK at `/health/ready`. Saved after one edit to the first output: a reference to a local-only design note, "(ADR-017)", was removed from the comment |
| `ci.yml.draft` | `.github/workflows/ci.yml` (repository root) | 2026-10-02 | Issue #77: a backend CI job that runs ruff and pytest with coverage against a PostgreSQL service |
| `ci-frontend-job.yml.draft` | `frontend` job in `.github/workflows/ci.yml` | 2026-10-02 | Issue #77: a frontend CI job that runs npm ci, lint, test:coverage and build |
| `ci-package-job.yml.draft` | `package` job in `.github/workflows/ci.yml` | 2026-10-02 | Issue #77: build the backend image tagged with the commit SHA and `week6` after the test jobs pass |
| `logging_setup.py.draft` | `backend/logging_setup.py` | 2026-10-02 | Issue #80: a JSON log formatter that tags each record with the request ID from a context variable |
| `request_logging.py.draft` | `backend/request_logging.py` | 2026-10-02 | Issue #80: middleware that assigns or propagates a request ID and logs one JSON line per request |
| `nginx-log-format.conf.draft` | `log_format no_query` in `backend/gateway/nginx.conf` | 2026-10-02 | Issue #80: a gateway access log format that leaves the query string out |
| `event-logging.py.draft` | `_login_failed` and the login events in `backend/main.py`, `coverage_created` in `backend/coverages.py`, `unexpected_error` in `backend/errors.py` | 2026-10-02 | Issue #80: log login success and failure, coverage creation and unexpected errors as structured events |
| `metrics.py.draft` | `backend/metrics.py` | 2026-10-02 | Issue #81: Prometheus request count and latency by route template, served at /metrics |
| `nginx-metrics-block.conf.draft` | `location ^~ /metrics` in `backend/gateway/nginx.conf` | 2026-10-02 | Issue #81: keep /metrics off the public gateway path |
| `prometheus.yml.draft` | `observability/prometheus/prometheus.yml` and the `prometheus` service in `backend/docker-compose.yml` | 2026-10-02 | Issue #81: scrape the API from inside the compose network |
| `grafana.yml.draft` | `observability/grafana/provisioning/` and the `grafana` service in `backend/docker-compose.yml` | 2026-10-02 | Issue #81: Grafana with the data source and dashboard provisioned from files, read-only |
| `grafana-dashboard.json.draft` | `observability/grafana/dashboards/api.json` | 2026-10-02 | Issue #81: request rate, 4xx/5xx error rate, p95 latency, coverages created, logins, and three SLO panels |
| `slo-alerts.yml.draft` | `observability/prometheus/rules/slo-alerts.yml` | 2026-10-02 | Issue #82: one Prometheus alert per SLO, with burn-rate thresholds and runbook links |
| `ci-alert-rules-job.yml.draft` | `alert-rules` job in `.github/workflows/ci.yml` | 2026-10-02 | Issue #82: check the Prometheus config and rules, and run the promtool rule tests, in CI |
| `runbooks.md.draft` | `docs/runbooks/*.md` (three files, concatenated in the draft) | 2026-10-02 | Issue #82: one runbook per alert: symptom, panels, causes, mitigation, follow-up |
| `frontend-image.draft` | `frontend/Dockerfile`, `frontend/nginx.conf`, `frontend/.dockerignore` | 2026-10-02 | Issue #78: a multi-stage frontend image served by unprivileged Nginx |
| `gateway-frontend-routing.draft` | `backend/gateway/nginx.conf` routing and the `frontend` service in `backend/docker-compose.yml` | 2026-10-02 | Issue #78: send the API paths to the API and everything else to the SPA through one gateway |
| `ci-frontend-image.yml.draft` | frontend steps of the `package` job in `.github/workflows/ci.yml` | 2026-10-03 | Issue #78: build, smoke-test and check the frontend image in CI with the backend tag scheme |
| `ci-audit-job.yml.draft` | `audit` job in `.github/workflows/ci.yml` | 2026-10-03 | Issue #79: audit backend and frontend dependencies for known vulnerabilities, and fail if a `.env` file is tracked |
| `ci-trivy-scan.yml.draft` | Trivy step of the `package` job in `.github/workflows/ci.yml` | 2026-10-03 | Issue #79: scan the backend and frontend images with Trivy and fail on fixable HIGH or CRITICAL findings |
| `Dockerfile-hardening.draft` | `backend/Dockerfile` (pip removal in both stages, `apt-get upgrade` in the runtime stage) | 2026-10-03 | Issue #79: clear the fixable HIGH findings Trivy reports in the backend image |
