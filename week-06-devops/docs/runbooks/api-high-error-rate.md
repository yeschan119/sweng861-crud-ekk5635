# Runbook: ApiHighErrorRate

**Alert:** more than 7.2% of `/api/*` requests ended in 5xx over 5 minutes, at more than
0.1 requests per second, for 2 minutes. That spends the 0.5% error budget of the
availability SLO (≥ 99.5% non-5xx over 7 days) 14.4 times too fast.
**Severity:** page.

## 1. Confirm the symptom

Open Grafana at http://127.0.0.1:3000, dashboard *SWENG 861 · API*.

- **SLO · API availability** is red or falling.
- **Error rate: 4xx vs 5xx**: the 5xx line has risen. If only the 4xx line moved, this alert should not have fired, so check the rule.
- **Request rate by route**: find which route the failures are on.

## 2. Tell the API failing from a dependency failing

The status code tells you who failed. Run these from `week-06-devops/backend`:

```bash
docker compose logs api --since 15m --no-log-prefix \
  | grep '"event": "request"' | grep -E '"status": 5[0-9][0-9]' | tail -20
```

| What you see | Likely cause |
|---|---|
| `500` on most `/api/coverages*` routes, with `unexpected_error` lines | The database is unreachable, or a bug |
| `503` or `502` only on `/api/coverages/{coverage_id}/financials`, with `upstream failure` lines | SEC EDGAR is down or slow. This service is working |
| `500` only on one route, after a deploy | A regression in that route |

Take an `incident` id from a 500 response or log line and read its traceback:

```bash
docker compose logs api --no-log-prefix | grep '<incident id>'
```

## 3. Check the database

```bash
docker compose ps db                      # expect "healthy"
curl -s http://127.0.0.1:8000/health      # {"status":"UP","db":"UP"} when reachable
```

## 4. Mitigate

| Cause | Action |
|---|---|
| Database stopped | `docker compose start db`, then confirm `/health` reports `db: UP` |
| Database paused or hung | `docker compose restart db` |
| SEC EDGAR outage | Nothing to restart. The API already answers 503 with `Retry-After`. Record the window; see the note below |
| Regression after a deploy | Roll back to the previous image tag (`sweng861-week6-backend:<previous sha>`) and recreate the API: `docker compose up -d api` |

The alert resolves by itself once the 5-minute ratio drops back under 7.2%.

## 5. Afterwards

Record the following:

- the start and end time, taken from the error rate panel;
- the routes affected;
- the cause, with one `incident` id and one `request_id`;
- an estimate of the error budget spent.

If an SEC EDGAR outage caused it, note that upstream 5xx count against this SLO today. Consider whether the SLI should leave out `502` and `503` from the financials route.
