# Week 2 — Authentication & Protected APIs

> Moved from the root README on 2026-09-23, unchanged apart from this note. The root README keeps the summary and the commands.


Source: `week-02-auth/`. The Week 1 service is unchanged; this is a separate
FastAPI application that adds a login flow, a user store, and a protected
endpoint.

## Authentication Strategy

**Option A — Social login with Google (OAuth 2.0 / OpenID Connect,
authorization code flow).** I chose it because the assignment's own framing is
that engineers integrate authentication rather than build it, and because the
semester project already commits to Google OIDC, so this is the layer the
later weeks build on rather than a detour. Option D would have meant storing
passwords, which is a liability this application has no reason to accept when
a real identity provider is available. Option B or C would have handed the
handshake to an SDK; doing the three legs directly is what the learning
objective asks me to be able to explain. The libraries used are deliberately
narrow: `httpx` for the token exchange and `PyJWT` for signature verification
against Google's published keys, so the flow itself stays visible in this
repository.

The flow in one sentence: the user clicks *Log in with Google*, is redirected
to Google, consents, and comes back to this backend with an authorization
code; the backend exchanges that code for tokens over a back channel, verifies
the ID token, creates or updates a local user row, and issues its own JWT that
the client then sends to protected APIs.

Step by step:

- **Client → `/auth/login`** — the backend generates `state`, `nonce`, and a
  PKCE verifier, stores them in short-lived HttpOnly cookies, and redirects.
- **→ Google** — the authorization request carries `client_id`,
  `redirect_uri`, `response_type=code`, `scope=openid email profile`, `state`,
  `nonce`, and the S256 `code_challenge`.
- **Google → `/auth/callback`** — the user returns with `code` and `state`.
  The backend rejects the request unless `state` matches the cookie.
- **Backend → Google token endpoint** — a direct server-to-server POST with
  the authorization code, the client secret, and the PKCE verifier.
- **Token validation** — the `id_token` is verified for signature (against
  Google's JWKS), issuer, audience, expiry, and nonce before any claim is read.
- **User persistence** — the row keyed on the Google `sub` is created or
  updated in PostgreSQL, and `last_login_at` is stamped.
- **Session token** — the backend signs its own JWT (subject = local user id)
  and returns it as `access_token`.
- **Protected API** — the client calls `/api/hello` with
  `Authorization: Bearer <token>`.

## Protected Endpoint

`GET /api/hello` is the secured endpoint. It declares the `require_auth`
dependency, which reads the bearer token from the `Authorization` header,
verifies its signature with the application's signing key, pins the algorithm
and the issuer, requires the standard claims to be present, and returns an
`AuthenticatedUser` carrying the local user id and email. Any failure — a
missing header, a malformed or expired token, a bad signature, a foreign
issuer — produces the same `401` with
`{"error": "Unauthorized", "message": "Valid access token is required"}` and a
`WWW-Authenticate: Bearer` header. With a valid token the handler answers `200`
with `{"message": "Hello, <email>!"}`, taking the email from the token rather
than from any request parameter. `require_auth` is a dependency rather than
ASGI middleware so that protection is declared on the routes that need it and
the default for a new route is closed. `/health` is intentionally left open,
because a liveness probe cannot log in.

## OWASP API Security Practices Applied

- **Broken Object Level Authorization (API1)** — the identity is taken only
  from the verified token. No user identifier is accepted from the path, the
  query string, or the body, so there is nothing for a caller to change in
  order to be answered as another user. The same rule becomes the `owner_id`
  filter when Week 3 adds records.
- **Excessive Data Exposure (API3)** — the endpoint returns one sentence, not
  the user record or the token's claims, and the session JWT itself carries
  only the subject, the email, and the time claims. A JWT is signed but not
  encrypted, so anything placed in it is readable by whoever holds it.
- **Security Misconfiguration (API7)** — every authentication failure returns
  the same generic message with no stack trace or internal detail; the reason
  stays server-side. Secrets are read from the environment, `.env` is
  git-ignored, and the state cookies are HttpOnly, SameSite=Lax, path-scoped,
  and Secure whenever the redirect URI is HTTPS.

## Bonus Features

**Rate limiting and suspicious-activity logging.** `/auth/login` and
`/auth/callback` allow ten requests per address per minute; the eleventh
returns `429` with a `Retry-After` header and a generic body. These endpoints
are unauthenticated by definition and each one costs an outbound request to
Google, which makes them the cheapest thing in the application to abuse.

Rejected tokens are counted separately from login attempts, so a burst of one
cannot mask the other. A single `401` is logged at info level; twenty or more
from one address inside a minute raises a warning that names the address and
the count, which is the pattern worth an operator's attention rather than the
individual failure.

The window slides rather than resetting on a fixed boundary, because a fixed
window lets a caller send a full allowance on either side of the boundary and
pass at twice the intended rate. Counters live in the process, which is
honest for a single worker and stated as a limitation: several workers each
keep their own, so an exact global limit needs a shared store such as Redis —
Week 6 work, alongside forwarding these logs to the observability stack.

The client address comes from the connection, not from `X-Forwarded-For`. A
caller can put anything in that header, so trusting it would let an attacker
reset their own counter at will; a deployment behind a proxy needs the proxy
configured as trusted instead.

## Additional Hardening

Beyond the required `state` parameter, the flow also uses **PKCE (S256)** and a
**nonce**. The authorization code travels through the browser and can be left
behind in a server log — it appeared in this project's own uvicorn access log
during testing — so PKCE ensures that whoever redeems a code must present the
verifier whose hash was published when the flow started. The nonce binds the
ID token to this browser's login attempt, so a previously issued token cannot
be replayed at the callback.

## Run Locally

```bash
cd week-02-auth/backend

cp .env.example .env          # then fill in GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET
docker compose up -d          # PostgreSQL

python3 -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

uvicorn main:app --port 8000
```

Open `http://localhost:8000/`. Requires Python 3.10+, Docker, and a Google
OAuth 2.0 client whose **Authorized redirect URI** is exactly
`http://localhost:8000/auth/callback`.

### Endpoints

| Method | Path | Auth | Response |
| ------ | ---- | ---- | -------- |
| GET | `/` | — | Login page |
| GET | `/health` | — | `{"status": "ok"}` |
| GET | `/auth/login` | — | `302` to Google (10/min per address, then `429`) |
| GET | `/auth/callback` | — | `{"access_token": "...", "token_type": "bearer", "expires_in": 3600}` |
| GET | `/api/hello` | Bearer | `{"message": "Hello, <email>!"}` / `401` |

### Tests

```bash
cd week-02-auth/backend
.venv/bin/python -m pytest tests/ -v
```

Sixteen tests, no database and no network — verified by running the suite with
socket connections blocked:

- the required unauthenticated `401` and authenticated `200`, and that
  `/health` stays public;
- seven rejected tokens: expired, signed with another key, a forged issuer,
  missing `exp`, `alg=none`, a payload edited to another user id under an
  intact signature, and a string that is not a token;
- the rate limiter: requests up to the limit pass, the next is `429` with
  `Retry-After`, one address cannot consume another's allowance, login and
  token-failure counters stay separate, and a burst of rejected tokens raises
  exactly one warning where a single failure raises none.

### AI Usage

Claude Code was used to draft this service. I directed it one piece at a time —
configuration, database, each leg of the flow, the auth gate, the endpoint,
the tests — and reviewed each piece before the next, which is why the security
decisions are recorded in the code comments and the commit messages rather
than only in this file. I chose the strategy (Option A), the libraries, the
additions of PKCE and the nonce, and the bonus feature. Every claim above was verified by running
it: the login against real Google credentials, the rejection paths with curl,
and the token cases in the test suite.
