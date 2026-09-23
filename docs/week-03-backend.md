# Week 3 — CRUD, External Data, and Error Handling

> Moved from the root README on 2026-09-23, unchanged apart from this note. The root README keeps the summary and the commands.


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
