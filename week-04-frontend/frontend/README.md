# frontend

This template should help get you started developing with Vue 3 in Vite.

## Recommended IDE Setup

[VS Code](https://code.visualstudio.com/) + [Vue (Official)](https://marketplace.visualstudio.com/items?itemName=Vue.volar) (and disable Vetur).

## Recommended Browser Setup

- Chromium-based browsers (Chrome, Edge, Brave, etc.):
  - [Vue.js devtools](https://chromewebstore.google.com/detail/vuejs-devtools/nhdogjmejiglipccpnnnanhbledajbpd)
  - [Turn on Custom Object Formatter in Chrome DevTools](http://bit.ly/object-formatters)
- Firefox:
  - [Vue.js devtools](https://addons.mozilla.org/en-US/firefox/addon/vue-js-devtools/)
  - [Turn on Custom Object Formatter in Firefox DevTools](https://fxdx.dev/firefox-devtools-custom-object-formatters/)

## Type Support for `.vue` Imports in TS

TypeScript cannot handle type information for `.vue` imports by default, so we replace the `tsc` CLI with `vue-tsc` for type checking. In editors, we need [Volar](https://marketplace.visualstudio.com/items?itemName=Vue.volar) to make the TypeScript language service aware of `.vue` types.

## Customize configuration

See [Vite Configuration Reference](https://vite.dev/config/).

## Project Setup

```sh
npm install
```

### Compile and Hot-Reload for Development

```sh
npm run dev
```

### Type-Check, Compile and Minify for Production

```sh
npm run build
```

### Run Unit Tests with [Vitest](https://vitest.dev/)

Unit and component specs run in jsdom with the API module mocked; no backend is needed.

```sh
npm run test:unit
```

### Lint with [ESLint](https://eslint.org/)

```sh
npm run lint
```

## Quality gates

Three commands, each meant to exit non-zero when the gate fails.

```sh
npm run test:coverage   # unit + component specs with v8 coverage; fails below 80% statements/branches/functions/lines
npm run lint            # oxlint + eslint, check only (npm run lint:fix rewrites files)
npm run type-check      # vue-tsc --build
```

Coverage counts application code under `src/` and leaves out `src/main.ts` (wiring only) and the specs themselves. The HTML report lands in `coverage/`.

## Integration test

`src/__tests__/integration/client.integration.spec.ts` drives the real API client against the running Week 4 stack: a signed-out request must answer 401, then a valid session creates, reads and lists a coverage and is refused a duplicate (409). The row it creates is deleted at the end.

It needs a session token for an existing user. Mint one exactly as `/auth/callback` does, from inside the API container:

```sh
# user and database names come from backend/.env (POSTGRES_USER, POSTGRES_DB)
docker exec sweng861-week4-db psql -U <POSTGRES_USER> -d <POSTGRES_DB> -c "select id, email from users"
docker exec sweng861-week4-api-1 python -c "from models import User; from tokens import issue_session_token; print(issue_session_token(User(id=<id from above>, email='<that email>')))"
```

Then run, without writing the token anywhere:

```sh
TEST_SESSION_TOKEN=<token> npm run test:integration
```

Without `TEST_SESSION_TOKEN` the spec is skipped, so the unit gate above never depends on a backend. `API_BASE_URL` overrides the default `http://localhost:8000`.

## AI usage

Vue components, the API client, validation, styles and their specs were drafted with Claude Code one piece at a time, then reviewed, run in the browser against the Week 4 stack and adjusted by the author; decisions are recorded in the course repository's architecture notes.
