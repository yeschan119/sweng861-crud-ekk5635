# Runbook: LoginServiceFailures

**Alert:** more than 14% of eligible logins failed for a server-side reason over 30
minutes, with at least 5 attempts, for 5 minutes. The login SLO is ≥ 99% over 7 days.

A failure is server-side when one of these happens:

- the token exchange with Google fails;
- verification of Google's id_token fails;
- the callback crashes with a 5xx.

Declined consent, expired login cookies and forged state are the caller's doing. They are not counted.
**Severity:** page. Nobody can sign in.

## 1. Confirm the symptom

Open Grafana, dashboard *SWENG 861 · API*, and check these panels:

- **SLO · Login success rate** is red.
- **Logins by outcome**: `service_error` is rising and `succeeded` is falling.
  - A `client_error` spike with `succeeded` steady is not this alert. It is forged or replayed callbacks, so look at rate limiting instead.

## 2. Read the reason

Every failed login is logged with the check that refused it. Run this from `week-06-devops/backend`:

```bash
docker compose logs api --since 30m --no-log-prefix \
  | grep '"event": "login_failed"' | grep -o '"reason": "[^"]*"' | sort | uniq -c
```

| Reason | Likely cause |
|---|---|
| `oidc_error:HTTPStatusError` | Google refused the token exchange. Usually the client secret was rotated or revoked, or the redirect URI no longer matches the OAuth client |
| `oidc_error:ConnectError` or `ReadTimeout` | Google cannot be reached from the API container (network or DNS) |
| `oidc_error:ExpiredSignatureError` or `ImmatureSignatureError` | The host clock has drifted |
| `oidc_error:InvalidAudienceError` | `GOOGLE_CLIENT_ID` does not match the OAuth client the browser used |
| 5xx on `/auth/callback` with `unexpected_error` | The callback crashed, usually because the database is down while the user row is saved. Follow the incident id |

## 3. Mitigate

| Cause | Action |
|---|---|
| Rotated or revoked secret | Put the current secret in `backend/.env` (never in a commit), then `docker compose up -d api` |
| Redirect URI or client id mismatch | Fix the OAuth client in Google Cloud Console, or `.env`, so they match `GOOGLE_REDIRECT_URI` |
| Clock drift | Resync the host clock; containers take it from the host |
| Database down | See [ApiHighErrorRate](api-high-error-rate.md), step 3 |
| Google outage | Nothing to restart. Record the window |

## 4. Afterwards

Record the following:

- the window;
- the reason counts from step 2;
- the cause;
- how many users could not sign in. Use the `succeeded` drop on the panel against the usual rate.
