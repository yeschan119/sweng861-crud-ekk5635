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
