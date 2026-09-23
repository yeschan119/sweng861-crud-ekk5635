# Week 4 — Front-End Application

> Moved from the root README on 2026-09-23, unchanged apart from this note. The root README keeps the summary and the commands.


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
