# Phase 16 — CI and security hardening

**Goal.** Every pull request runs the same automated checks, nothing risky can merge unnoticed, and the remaining security gaps (rate limits, headers, route authorization, resource limits, data deletion) are closed before BodhCode goes on the internet.

No new product features. Where an earlier phase said "Phase 16" for rate limiting, this is it.

## Aapko karna hai (before you paste the prompt)

- [ ] Phase 15 (evals) pass ho chuka hai.
- [ ] `git checkout -b phase-16`.
- [ ] GitHub repo → Settings → Secrets and variables → Actions mein add karo: `GROQ_API_KEY`, `LANGSMITH_API_KEY` (sirf eval workflow ke liye; normal CI ko inki zaroorat nahi).
- [ ] GitHub repo → Settings → Branches mein `main` ke liye protection rule banao (agent ke baad aap karoge): "Require a pull request", "Require status checks" (CI), aur CodeRabbit ka review padhne ki aadat.
- [ ] GitHub repo → Settings → Code security mein Dependabot alerts on karo.

## Build

### 1. Continuous integration (`.github/workflows/`)
- `ci.yml`, on every pull request and on push to `main`:
  - **backend job:** Python 3.12 + `uv`, `uv sync --frozen`, `ruff check`, `ruff format --check`, `pytest -q` with a SQLite config and **no secrets**, then an Alembic check: `alembic upgrade head` on an empty database succeeds and autogenerate shows **no drift** between models and migrations.
  - **frontend job:** Node 20 + pnpm (cached), `pnpm install --frozen-lockfile`, `pnpm lint`, `pnpm test`, `pnpm build`.
  - **secret scan job:** `gitleaks` (or equivalent) over the repo history of the PR.
  - `permissions: contents: read` at the top level; third-party actions pinned to a major version (or a commit SHA); a `concurrency` group that cancels superseded runs.
- `evals.yml`: `workflow_dispatch` plus a nightly schedule. Suites A, B, E run **without secrets**. Suites C and D run with `GROQ_API_KEY` / `LANGSMITH_API_KEY` **only on `main` or manual runs, never on pull requests from forks**. Results uploaded as a workflow artifact; the job fails if thresholds are not met.
- `audit.yml`: weekly `pip-audit` and `pnpm audit`; results are reviewed by a human and do **not** auto-fail pull requests.
- `.github/dependabot.yml` for `pip`/`uv`, `npm`, and `github-actions` (weekly).
- Update `.coderabbit.yaml` `path_instructions` for the new areas and keep them aligned with `AGENTS.md`: `backend/app/ai/tools/**`, `backend/app/skills/**`, `backend/app/github/push.py`, `backend/evals/**`, and `.github/workflows/**` ("no secrets in logs, least-privilege permissions, pinned actions").
- `CONTRIBUTING.md`: how phases, branches, PRs, CI and CodeRabbit work together.

### 2. Rate limiting
`slowapi` or a small DB/memory limiter, keyed by **user id** (never by token):
- translations 60/min; chat and agent turns 20/min and 200/day; explain 30/min; repo ingests 10/hour; push / issue / comment limits as defined in Phase 14.
- per-IP limit on `/auth/*` (30/min).
- 429 responses include `Retry-After`; the frontend shows a friendly "slow down" message with a countdown.

### 3. Security headers and CORS
- API middleware sets `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Cache-Control: no-store` on authenticated JSON, and a `Content-Security-Policy` for any HTML the API serves.
- Frontend host headers (documented here, applied in Phase 17): CSP allowing only `self`, the API origin, `avatars.githubusercontent.com`, and Monaco's assets; `frame-ancestors 'none'`; a minimal `Permissions-Policy`; HSTS in production.
- Re-verify CORS: exactly one allowed origin (`FRONTEND_URL`), credentials allowed, no wildcard.

### 4. Authorization and CSRF audits (as tests)
- A test that enumerates **all** routes and asserts every non-public route depends on `get_current_user`; the public list is an explicit allow-list in the test (`/health`, `/ready`, `/meta/languages`, `/auth/github/login`, `/auth/github/callback`, …).
- A test that enumerates all `POST/PUT/PATCH/DELETE` routes and asserts the `X-Requested-With` CSRF dependency is present (OAuth callback and logout handled explicitly).
- A parametrized **ownership test** for every route containing a repo/proposal/skill/preview id, using two users: user B always gets 404.
- Adding a route without auth or CSRF makes these tests fail.

### 5. Secrets, egress and resource limits
- Production boot guard: with `ENV=production`, the process refuses to start if `APP_SECRET_KEY` / `TOKEN_ENCRYPTION_KEY` equal known dev placeholders, are too short, or if `FRONTEND_URL` / `BACKEND_URL` are not `https`.
- Egress test: the HTTP client factories may only use base URLs for `api.github.com`, `codeload.github.com`, Groq and LangSmith; no user-supplied URL is ever fetched.
- Request body limit (1.5 MB default, 20 KB for skill import), SSE maximum duration, a cap on concurrent background tasks.
- `DATA_DIR` disk quota: evict least-recently-used cached repos beyond a configurable size (default 5 GB), never evicting a repo whose status is `fetching` or `analyzing`.
- A daily cleanup sweep (startup task or scheduled job) removes expired `PushPreview` rows and old `TranslationCache` rows, and resets repos stuck in `fetching`/`analyzing` for more than 30 minutes.

### 6. "Delete my data"
- `POST /auth/disconnect` (CSRF + auth): deletes the stored token, the user's repos links, working files, proposals, previews, skills, action logs and the user row, then clears the session. Shared public-repo cache directories are not user data and stay.
- Settings → "Privacy & data": explains what is stored (profile fields, encrypted token, settings, working copies, proposals, skills, activity log), the OAuth scopes requested and why, and a **Delete my data** button with a typed confirmation.
- `SECURITY.md`: how to report vulnerabilities, what is stored, what scopes are used. Every claim must match the code.

### Tests
- Rate limit returns 429 + `Retry-After` and resets after the window; limits are per user, not global.
- Headers present on API responses.
- Route-audit and ownership tests described above.
- Production boot guard (placeholder secret → exit).
- Egress allow-list test.
- Cleanup sweep: expired previews removed, active ones kept, stuck repos reset.
- `POST /auth/disconnect`: all of the user's rows gone, other users untouched, session cleared, second call → 401.

## Constraints

- **CI never needs production secrets.** LLM-dependent jobs run only on trusted refs (`main`/manual), never on fork PRs.
- Least privilege everywhere: GitHub Actions `contents: read` by default; OAuth scopes unchanged; no new permissions are requested anywhere.
- Rate-limit counters, logs and traces key on user id, never on tokens or emails.
- Do not weaken any earlier constraint (review-before-apply, untrusted-data handling, path safety) to make something easier.
- No new product features and no new tables except what "Delete my data" and rate limiting strictly need (prefer in-memory/DB counters already available).
- Every statement in `SECURITY.md` and `CONTRIBUTING.md` must match what the code and workflows do.

## Order of work

1. Route-audit tests (auth, CSRF, ownership) — they will immediately show any gaps; fix the gaps.
2. Production boot guard and egress test.
3. Rate limiting + frontend 429 handling.
4. Security headers; resource limits; cleanup sweep.
5. `POST /auth/disconnect` and the Privacy page; `SECURITY.md`.
6. Workflows (`ci.yml`, `evals.yml`, `audit.yml`), Dependabot, `CONTRIBUTING.md`, `.coderabbit.yaml` update.
7. Open the PR and watch CI + CodeRabbit run on it.

## Acceptance check

1. Open a PR with a deliberate lint error: **CI fails**. Fix it: CI is green. CodeRabbit comments on the same PR.
2. Add a route without `get_current_user` (or a mutating route without the CSRF dependency): the audit tests fail. Remove it.
3. The Alembic drift check fails if you change a model without a migration (try it, then revert).
4. Hit an LLM endpoint 70 times in a minute: you get `429` with `Retry-After` and the UI shows a friendly message; another user is unaffected.
5. Response headers on the API show `nosniff`, referrer policy and `no-store` for authenticated JSON.
6. Start with `ENV=production` and a placeholder `APP_SECRET_KEY`: the process refuses to start naming the variable.
7. The nightly/manual `evals.yml` run uploads results; a fork PR cannot access the Groq/LangSmith secrets (verify by reading the workflow conditions).
8. `gitleaks` job fails if you commit a fake `ghp_…` token in a test branch (try, then remove from history).
9. "Delete my data": after typing the confirmation, your account, token, working copies and proposals are gone; signing in again starts clean; another user's data is untouched.
10. `pip-audit` / `pnpm audit` workflow runs and posts its report without failing PRs.
11. Everything from earlier phases still passes: `uv run pytest`, `ruff`, `pnpm lint`, `pnpm test`, `pnpm build`.

## Not in this phase

Dockerfile, hosting, environment variables for production, DNS, production OAuth App (Phase 17). New product features. Private repo support. Billing or quotas beyond the rate limits above.

## Paste this to the agent

```text
Read AGENTS.md, then this entire file (16-ci-and-security.md).
Implement exactly "Build", obey "Constraints", follow "Order of work".
Do not implement anything under "Not in this phase".
For anything that needs my GitHub settings (secrets, branch protection, Dependabot alerts), write the exact click-by-click steps for me instead of asking me to paste secrets into the chat.
Finish by running the Acceptance check where automatable, report PASS / FAIL / NEEDS MANUAL TEST per item, list commands I must run, then stop.
```
