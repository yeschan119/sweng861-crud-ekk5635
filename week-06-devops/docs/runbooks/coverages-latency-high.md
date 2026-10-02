# Runbook: CoveragesLatencyHigh

**Alert:** the p95 latency of `GET /api/coverages` was above 500 ms over 5 minutes, for
5 minutes. The latency SLO is p95 ≤ 500 ms over 7 days.
**Severity:** ticket. Users get a slower list, not errors.

## 1. Confirm the symptom

Open Grafana, dashboard *SWENG 861 · API*, and check these panels:

- **SLO · GET /api/coverages p95** is red.
- **p95 latency by route**: see whether only `/api/coverages` is slow, or every route is.
- **Error rate: 4xx vs 5xx**: see whether 5xx follow the latency. They usually do when the database stops answering.

## 2. Find where the time goes

`GET /api/coverages` reads one table, scoped to the caller. It calls nothing external, so a slow list means a slow database or a busy API process. Run these from `week-06-devops/backend`:

```bash
# Slowest recent list requests
docker compose logs api --since 15m --no-log-prefix \
  | grep '"path": "/api/coverages"' | grep '"method": "GET"' \
  | python3 -c 'import sys,json; r=sorted((json.loads(l) for l in sys.stdin), key=lambda e: -e["duration_ms"]); [print(e["duration_ms"], e["status"], e["request_id"]) for e in r[:10]]'

docker compose ps db          # "healthy"?
docker stats --no-stream      # CPU or memory pressure on api or db?
```

| What you see | Likely cause |
|---|---|
| Every route is slow, and the db is unhealthy or paused | The database |
| Only `/api/coverages` is slow, and duration grows with the account's size | Missing index, or a large result set |
| The API container is at 100% CPU | Load beyond one replica |

## 3. Mitigate

| Cause | Action |
|---|---|
| Database paused or hung | `docker compose restart db` |
| Load | Add a replica, `docker compose up -d --scale api=2`. The gateway balances across it, and Prometheus scrapes both |
| Query or result size | Open an issue with the slow `request_id` lines. A fix is a code change |

## 4. Afterwards

Record the following:

- the window;
- the peak p95, from the panel;
- the cause;
- whether 5xx followed. If they did, the availability SLO was spent too.
