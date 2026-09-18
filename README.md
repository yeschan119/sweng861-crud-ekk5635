# sweng861-crud-ekk5635

**Eungchan Kang**

SWENG 861 – Software Construction

## Planned CRUD App

A CRUD API and web UI where each user writes and maintains their own company
analysis notes. Financial figures are pulled from SEC EDGAR filings to support
each note.

## Backend — Hello/Health API (Week 1, Assignment 3)

FastAPI service in `week-01-setup/backend/`.

### Run locally

```bash
cd week-01-setup/backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Requires Python 3.10 or newer.

### Endpoints

| Method | Path | Response |
| ------ | ---- | -------- |
| GET | `/health` | `{"status": "ok"}` |
| GET | `/api/hello` | `{"message": "Hello, World!"}` |

Interactive API docs are served at `http://127.0.0.1:8000/docs`.

### Verify

```bash
curl -i http://127.0.0.1:8000/health
curl -i http://127.0.0.1:8000/api/hello
```

Both return `200 OK` with `content-type: application/json`.

### AI usage

The first draft of `main.py` was written with Claude Code. I reviewed the
routing and return types line by line, deliberately kept `/health` outside the
`/api` prefix because it is an infrastructure probe rather than an application
feature, and verified both endpoints with curl before committing.

---

# Week 2 — Authentication & Protected APIs

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

---

# Week 3 — CRUD, External Data, and Error Handling

Source: `week-03-backend/`. The Week 2 authentication layer is carried over
unchanged; this week adds an owned resource, the third-party data behind it,
and one error contract across every endpoint.

## Third-Party API — SEC EDGAR

I chose the SEC's EDGAR XBRL API (`data.sec.gov/api/xbrl/companyconcept`)
because this application's premise is that a company note cites real filing
figures, and EDGAR is where those figures are first published rather than a
reseller's copy of them. It is free, requires no account, and is maintained by
a regulator instead of by a vendor whose free tier can be withdrawn in the
middle of a semester. Its `companyconcept` endpoint answers with a small, flat
JSON document keyed by unit and period, which is a structure worth validating
field by field rather than a blob worth storing whole. The trade-off is
unusual failure behaviour, and both cases were measured against the live API
before the client was written: a concept the filer never reported answers
`404` with an **XML** body — so the status code is read before the body is
touched — and a `200` can carry a figure that is years out of date because an
accounting standard replaced the tag, which is why revenue is requested as an
ordered chain of two tags rather than as one.

EDGAR issues no API key. Its fair-access policy instead requires a
`User-Agent` header naming a real person to contact, and answers `403` without
one. The value read from `.env` is therefore `SEC_USER_AGENT`: not a secret,
but a personal address that differs per environment, so `.env.example` carries
only the variable name and a placeholder.

## API Gateway

Nginx, as a reverse proxy in front of the API, rather than a routing layer
inside FastAPI. The choice follows from what the assignment asks a gateway to
do — manage requests and responses — which only holds if requests cannot avoid
it. A layer inside the framework is the same process it is supposed to be
governing: it cannot terminate TLS, it cannot answer when the application is
down, and it cannot spread traffic across more than one copy of the
application, because there is only ever one. Nginx is also the smaller of the
two real options next to something like Traefik, in the sense that matters
here: its behaviour is one file a reader can follow, rather than conventions
about container labels that have to be known before the routing makes sense.

The API no longer publishes a host port. It is reachable only from inside the
compose network, so the rules stated at the gateway are not optional — a caller
cannot route around them by addressing the service directly. That also settles
something the containerisation step could not: two containers cannot hold one
host port, so a second copy of the API could not previously start at all. With
the gateway as the only published entry point, `docker compose up --scale
api=3` works and Nginx spreads requests across the replicas.

Getting that spreading to actually happen took a correction. Nginx resolves a
host name in an `upstream` block once, when it starts, and reuses that address
for the life of the process. Compose gives each replica its own address, so the
obvious configuration sends every request to whichever container existed first
and silently ignores the others — measured, with three replicas running and
Docker's DNS returning all three addresses, twelve requests went twelve times
to the same one. Naming Docker's resolver and putting the upstream in a
variable moves the lookup to request time; the same twelve requests then split
5/4/3, and scaling up or down afterwards is picked up without restarting the
proxy.

Failures answer in the API's own shape. If no replica is reachable, Nginx would
normally return its own HTML error page, which is a second error format for
clients to handle and reveals that the thing behind the door is Nginx. Instead
it answers `{"error", "message"}` with `Retry-After`, the same contract every
other failure in this service uses. The gateway keeps a separate health
endpoint that does not touch the API, because "the gateway is down" and "the
API is down" are the two states an operator most needs to tell apart, and a
probe that proxied through would report them identically.

Client addresses are forwarded as `X-Real-IP` and `X-Forwarded-For`, but the
application still reads the connection address for rate limiting, as Week 2
decided. A client can put anything in those headers, so trusting them lets a
caller reset their own rate-limit counter; making the application read them is
a decision that belongs to a deployment which knows this proxy is the only way
in, and it is recorded here rather than switched on quietly.

## Access Control — the Public, Authenticated, and Admin Boundary

Three bands, and every route sits in exactly one of them.

| Band | Routes | Gate |
|---|---|---|
| Public | `GET /health`, `GET /auth/login`, `GET /auth/callback`, `GET /` | none |
| Authenticated | `GET`/`POST /api/coverages`, `GET`/`PATCH`/`DELETE /api/coverages/{id}`, `POST`/`GET /api/coverages/{id}/financials`, `GET /api/hello` | `require_auth`, then scoped to the caller's `owner_id` |
| Admin | `GET /api/admin/coverages` | `require_auth`, then `require_admin` |

The public band is small on purpose and holds nothing belonging to anyone. A
health probe cannot carry a token, because the container runtime that calls it
has no account; the two `/auth` routes are how a caller gets a token in the
first place, so requiring one would be circular.

The assignment offers reading a list as its example of a public endpoint, and
this application does not follow that example. It is worth saying why rather
than quietly diverging. Every query here is scoped by `owner_id`: a coverage
belongs to the analyst who created it, and the whole of the multi-tenancy
requirement is that no query answers without that term. An unauthenticated
caller has no `owner_id`, so a public `GET /api/coverages` has no defensible
answer — returning every tenant's rows is precisely the leak the scoping
exists to prevent, and returning an empty list is an endpoint that pretends to
work. The example assumes a public catalogue with one shared set of rows. This
is a private workspace per analyst, and the honest boundary for it puts the
whole resource behind authentication.

What the admin role adds is a second question asked after the first. An
administrator is still authenticated; `require_admin` is layered on
`require_auth` rather than replacing it, so the token is verified once, by the
code that owns that job. The privilege it grants is deliberately narrow — one
route that lists every coverage regardless of owner.

That route is separate rather than a parameter on the tenant list, and the
reason is the same one that shapes the rest of this service. A `?all=true`
flag would make the ownership filter in `list_coverages` conditional, and a
filter that is applied only sometimes is a filter that will eventually be
skipped by accident. The tenant list stays unconditionally scoped; seeing
across tenants means asking a different question at a different URL, in a
module that cannot be reached without the admin dependency. It is also the one
response in the API that returns `owner_id`, because a list of every row with
no owner attached cannot be acted on, while a tenant never needs the column —
every row they can see is already theirs.

The role lives in the `users` table, not in the session token. A token is a
bearer credential that stays valid until it expires, so a role minted into one
would outlive the decision that granted it: an administrator demoted a minute
after signing in would keep administering for the remaining hour. Reading the
column means the answer is current at the moment the request is judged, and
the cost — one query — falls only on the routes that need it. The test that
pins this sends the *same* token twice, refused and then accepted, with
nothing changed between the two but the column.

A refused admin request answers `403`, while a request for another tenant's
row answers `404`. The two hide different things. The `404` hides whether a
row exists, because an id that answers differently from its neighbours is an
id an attacker can enumerate — for that case, "not yours" and "no such row"
are deliberately indistinguishable. The admin route keeps no such secret: it
is one fixed path, identical for every caller, and published in the OpenAPI
document. Answering `404` there would tell nobody anything except an
administrator who had just lost the role, who would conclude the feature had
been removed.

The database holds no password hash, which the assignment's schema sketch
asks for. Authentication is Google OIDC with the authorization code flow, so
this application never receives a password and has nothing to hash; it does
not store Google's access or refresh tokens either, since nothing here calls
Google on the user's behalf after login. That is a stronger position than the
sketch rather than a missing field — a credential that is never received
cannot be leaked from this table — and `ck_users_role` keeps the column that
*is* there honest, since a role the application does not know about cannot be
written even by hand at the `psql` prompt.

AI use: drafting, and reviewing the authorization trade-offs.

# Week 4 — Front-End Application

Source: `week-04-frontend/`. `backend/` is the Week 3 service with one change
for a browser client: after Google login, `/auth/callback` redirects to the
front end (`FRONTEND_URL`) with the session token in the URL fragment instead of
rendering a page. `frontend/` is a Vue 3 + TypeScript single-page app built with
Vite; its own README covers the test, lint and coverage commands in detail.

## Run Locally

Two processes: the API stack in Docker, the SPA from the Vite dev server.
Requires Docker, Node 22.18+ (or 24.12+), and the Google OAuth client from Week 2 with
`http://localhost:8000/auth/callback` as its authorized redirect URI.

```bash
# 1. API stack: PostgreSQL, one-shot migration, the API, and the Nginx gateway on :8000
cd week-04-frontend/backend
cp .env.example .env          # fill in GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, SESSION_JWT_SECRET,
                              # POSTGRES_PASSWORD, SEC_USER_AGENT; FRONTEND_URL defaults to http://localhost:5173
docker compose up -d --build
curl http://localhost:8000/health   # {"status":"ok"}

# 2. Front end on :5173, proxying /api and /auth to :8000
cd ../frontend
npm install
npm run dev
```

Open `http://localhost:5173/`, click **Login with Google**, and you land on
**My Coverages**. The Week 3 stack binds the same ports (8000, 5432), so stop it
first if it is running.

| Variable | Read by | Purpose |
|---|---|---|
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` | API | OpenID Connect client; the redirect URI must match the Google console exactly |
| `FRONTEND_URL` | API | Where the callback sends the browser after login (default `http://localhost:5173`) |
| `SESSION_JWT_SECRET`, `SESSION_JWT_TTL_SECONDS` | API | Signs the session token the SPA carries; 3600 s by default |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `DATABASE_URL` | compose, API | Database credentials; compose rewrites the host to `db` inside the network |
| `SEC_USER_AGENT` | API | Contact string SEC EDGAR requires |
| `TEST_SESSION_TOKEN`, `API_BASE_URL` | frontend integration test only | See `week-04-frontend/frontend/README.md` |

The front end has no environment file: it reaches the API through the Vite
proxy at the same origin, so no secret ever enters the bundle.

## Routing — Public and Protected

`/login` is the only public route. Everything else (`/coverages`,
`/coverages/new`, `/coverages/:id`, `/coverages/:id/edit`) is protected by
default: a route is public only when it says `meta: { public: true }`, so a
route added later cannot become public by omission. The guard sends a
signed-out visitor to `/login` and a signed-in one away from it. The
`RouterView` is keyed by path, so every navigation mounts a fresh page.

## Login Flow and Token Handling

1. **Login with Google** is a plain link to `/auth/login`; the API sets the
   PKCE and state cookies and redirects to Google.
2. Google returns to the API's `/auth/callback`, which verifies the id_token,
   upserts the user, mints the HS256 session JWT, and redirects to
   `FRONTEND_URL/login#access_token=…`.
3. `LoginView` reads the fragment once, stores the token in memory
   (`src/auth/session.ts`), strips it from the URL with `history.replaceState`,
   and goes to `/coverages`. A failed login arrives as `#error=login_failed`
   and shows one sentence.

The token lives only in memory: never in `localStorage`, cookies, or logs, so a
reload signs the user out. One client (`src/api/client.ts`) attaches
`Authorization: Bearer` to every request and parses the API's single error
shape. A **401** clears the session and the router moves to `/login`; a **403**
keeps the session and the page says "You are not authorized to view this
item."; a **404** says "This item does not exist or has been deleted."

## Asynchronous UX

Every remote call goes through `useRequest`, which owns the
loading / success / error cycle and discards a stale response when a newer one
lands. The list shows a loading line, an empty state, an error with **Retry**,
or the table; the detail page distinguishes 404 and 403 from other failures.
The form validates locally before sending (title required, CIK ten digits,
ticker at most ten characters), disables **Save** and shows "Saving…" while the
request runs, maps a 422 onto the fields the API names, shows the API's own
message on a 409, and otherwise "Could not save. Please try again." A
successful save navigates to the detail page with a notice that survives the
navigation and is cleared by the next one.

## Security

- No secret in the front end: `grep` over the built `dist/` for the secret
  names finds nothing; the command is under Quality gates in
  `week-04-frontend/frontend/README.md`.
- User data is rendered as text only; no `v-html`. Two specs render hostile
  HTML in a title and a description and assert no element is created.
- No token in web storage or the console; a spec asserts both after sign-in.
- The API remains the authority: `owner_id` comes from the token, cross-tenant
  rows answer 404, and the gateway is the only published port.

## Responsive Layout

One stylesheet (`src/assets/main.css`): a wrapping flex header, grid forms, a
60 rem column with a 16 px gutter, 44 px tap targets, and a card layout for the
list below 640 px so nothing scrolls horizontally at 375 px. Screenshots at
laptop and phone width are in `week-04-frontend/docs/screenshots/`.

## Screenshots

All in `week-04-frontend/docs/screenshots/`, captured against the running stack
at laptop width unless named otherwise.

| Checklist item | File |
|---|---|
| Login: page, success (the signed-in list it lands on), failure | `01-login.jpg`, `04-list-populated.jpg`, `02-login-failed.jpg` |
| List: loading, populated, error with retry | `03-list-loading.jpg`, `04-list-populated.jpg`, `05-list-error-retry.jpg` |
| Detail: success, 404, 403 | `06-detail.jpg`, `07-detail-404.jpg`, `08-detail-403.jpg` |
| Form: validation, edit, saving, 409, 422 field errors, post-save notice | `09-form-validation.jpg`, `10-form-edit.jpg`, `11-form-saving.jpg`, `12-form-409-duplicate.jpg`, `13-form-422-fields.jpg`, `14-form-saved-notice.jpg` |
| Phone width (375 px) | `15-phone-list.png`, `16-phone-detail.png`, `17-phone-login.jpg`, `18-phone-form-validation.png` |

The 403 and the 422 were produced by substituting the response in the browser,
because a signed-in user cannot reach another tenant's row (the API answers 404)
and the form's own validation mirrors the API's limits; everything else is a
real response from the API.

## Bonus Features

**Accessibility.** The shell exposes `header`, `nav` and `main` landmarks and a
"Skip to content" link as the first tab stop, which focuses `main` directly.
Every control has a visible label; a form error is tied to its input with
`aria-invalid` and `aria-describedby`, required fields are marked, and a failed
submit moves focus to the first invalid field. The list table has a caption and
column scopes, status and error messages use `role="status"` and
`role="alert"`, and a `:focus-visible` ring marks keyboard focus on every link,
button and field. Tab order on each page follows the reading order, so login,
list, detail, edit and save complete with the keyboard alone. Four specs pin the
wiring.

## Quality Gates

```bash
cd week-04-frontend/frontend
npm run test:coverage    # 102 tests; statements/branches/functions/lines all above the 80% threshold
npm run lint             # oxlint + eslint, check only
npm run type-check
TEST_SESSION_TOKEN=<token> npm run test:integration   # against the running stack; see the frontend README
```

AI use: the Vue components, API client, validation module, stylesheet and
their specs were drafted with Claude Code one piece at a time, then reviewed,
run in the browser against the Week 4 stack, and adjusted by the author.
