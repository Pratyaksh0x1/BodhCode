# Phase 17 — Deploy and document

**Goal.** BodhCode runs on the internet: a containerized backend with migrations, a static frontend, Postgres, a production GitHub OAuth App, cookies that actually work across the two hosts, and written instructions so someone else can reproduce the whole setup.

This is the last phase. It adds no features.

## Aapko karna hai (before you paste the prompt)

- [ ] Phases 1–16 ke acceptance checks pass ho chuke hain, CI green hai.
- [ ] `git checkout -b phase-17`.
- [ ] **Accounts banao:**
  - Backend hosting: Render / Railway / Fly.io (koi ek).
  - Frontend hosting: Vercel / Netlify / Cloudflare Pages (koi ek).
  - Postgres: Neon ya Supabase (sirf database ke liye).
  - Domain (optional, par cookies ke liye best: ek hi domain ke do subdomain).
- [ ] **Production ke liye alag GitHub OAuth App** (GitHub → Settings → Developer settings → OAuth Apps → New): Homepage URL = frontend URL, Authorization callback URL = `https://<backend-or-api-domain>/auth/github/callback`. (Ek OAuth App ka sirf ek callback URL hota hai, isliye dev wali app reuse nahi hogi.)
- [ ] **Naye secrets generate karo** (dev wale kabhi reuse mat karo):
  ```
  python -c "import secrets; print(secrets.token_urlsafe(48))"
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
  Pehla `APP_SECRET_KEY`, doosra `TOKEN_ENCRYPTION_KEY`. Inhe sirf hosting dashboard ke secret/env section mein paste karo, chat mein nahi.
- [ ] Docker Desktop install (image local par test karne ke liye).
- [ ] Hosting plan check karo: **persistent disk/volume** milti hai ya nahi (repo files `DATA_DIR` mein rehti hain). Free plans par disk aksar temporary hoti hai — Build section mein dono options hain.
- [ ] Groq/LangSmith ke production keys alag rakhna chaho to naye bana lo.

## Build

### 1. Backend container
- `backend/Dockerfile`: multi-stage, `python:3.12-slim`, `uv sync --frozen --no-dev`, runs as a **non-root** user, `HEALTHCHECK` hitting `/health`. `.dockerignore` excludes `.env*`, `*.db`, `data/`, `.venv`, tests and evals.
- Start command: `alembic upgrade head` **then** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Worker count from `WEB_CONCURRENCY` (default 1; note that in-memory caches and rate limiters are per process).
- `DATA_DIR` storage decision — choose one, implement it, document it:
  - **A (recommended):** mount a persistent volume at `DATA_DIR`.
  - **B:** treat `DATA_DIR` as ephemeral; ingestion and the editor must then recover from a missing cache (re-download by commit sha on demand, with a friendly "restoring files…" state). Working-copy edits live in the database, so they survive.
- `/health` (liveness, no dependencies) and `/ready` (database reachable **and** migrations at head; 503 otherwise).
- Structured JSON logs in production: request id, route, status, latency, user id; **never** bodies, headers, tokens or file contents.
- Build-time env `GIT_SHA` and `APP_VERSION` surfaced in `/health` and in LangSmith tags.

### 2. Postgres
- `DATABASE_URL` uses `postgresql+psycopg://…`; connection pool sizing and `pool_pre_ping` configured; SSL required when the provider needs it.
- Run the **entire test suite once against Postgres** (CI service container or a documented manual run) to catch SQLite-vs-Postgres differences: JSON columns, case-sensitive text comparisons, boolean defaults, `Unique` semantics with `NULL` (default skills use `user_id = NULL`), timestamp handling.
- Fix any differences found, and add the Postgres run to `ci.yml` if it is cheap enough.

### 3. Frontend build and hosting
- `VITE_API_URL` for production; `pnpm build` output deployed with an **SPA fallback** (`/* → /index.html`), hashed assets cached as immutable, `index.html` `no-cache`.
- Apply the CSP and security headers designed in Phase 16 in the host's header config (`_headers`, `vercel.json`, or equivalent).
- **Monaco loading — choose one and test it:**
  - allow `cdn.jsdelivr.net` in CSP and document it; or
  - **bundle Monaco locally** (`loader.config({ monaco })` + Vite worker setup) so no third-party script is needed (preferred when CSP is strict).
- No `console.log` of data in production builds; source maps disabled or uploaded privately.

### 4. Cookies across hosts (the part that usually breaks)
The session cookie is `HttpOnly; Secure; SameSite=Lax`. A frontend on `x.vercel.app` and an API on `y.onrender.com` are **different sites**, so the browser will not send the cookie on `fetch` calls. Fix with exactly one of:
- **Same registrable domain:** `app.example.com` (frontend) + `api.example.com` (API), cookie `Domain=example.com`, CORS allowing only `https://app.example.com`; or
- **Proxy under the frontend domain:** a host rewrite sends `/api/*` to the backend, so cookies are first-party; then `VITE_API_URL` is the frontend origin + `/api` and the OAuth callback URL on GitHub points to `https://<frontend-domain>/api/auth/github/callback`.
Do **not** use `SameSite=None` as a workaround (third-party cookie blocking breaks it). Document the chosen approach and test sign-in on the real URLs.

### 5. Production configuration table
`DEPLOY.md` must contain a table of every environment variable: name, required?, example (never a real value), where it is used, and which side (backend/frontend/CI). Include at least: `ENV`, `APP_SECRET_KEY`, `TOKEN_ENCRYPTION_KEY`, `FRONTEND_URL`, `BACKEND_URL`, `DATABASE_URL`, `DATA_DIR`, `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GROQ_API_KEY`, `GROQ_MODEL`, `GROQ_FAST_MODEL`, `LLM_MAX_CONCURRENCY`, `LANGSMITH_*`, `WEB_CONCURRENCY`, `GIT_SHA`, `APP_VERSION`, `VITE_API_URL`.

### 6. Documentation
- **`DEPLOY.md`:** step-by-step for the chosen hosts — create the database; create the production OAuth App; set environment variables/secrets; deploy the backend; confirm migrations ran; deploy the frontend; configure rewrites/domain and headers; verify cookies; run the smoke test; **rollback** steps; database **backup** advice; how to rotate secrets (and what that invalidates: rotating `TOKEN_ENCRYPTION_KEY` makes stored tokens unreadable — users must sign in again; rotating `APP_SECRET_KEY` signs everyone out).
- **`README.md` (final):** what BodhCode is, screenshots, a Mermaid architecture diagram, local setup, running tests and evals, the principle "the graph is never AI-generated", honest limitations (public repos only, TS/JS only, machine-translation caveats, graph reflects the original commit).
- Branch-protection recommendation recorded in `DEPLOY.md`: require CI + CodeRabbit before merge.

### Tests
- `/ready` returns 503 when the database is unreachable or migrations are behind; 200 otherwise.
- JSON log formatter: contains request id/route/status/latency, never headers/bodies/tokens (assert on captured output).
- Boot-time config checks for production from Phase 16 still pass in the container.
- Storage option B only: missing cache directory triggers re-fetch, not a crash.

## Constraints

- **No new features.** Do not weaken any earlier constraint to make deployment easier.
- Production secrets live **only** in the host's secret manager — never in the repo, the image, the build logs or the chat. Dev and prod credentials are different.
- The container runs as non-root and contains no `.env`, tests, or dev dependencies.
- The production database user is limited to the app's schema.
- Only `github.com` hosts, Groq and LangSmith are contacted (Phase 16 egress test stays green).
- Every statement in `README.md`, `SECURITY.md` and `DEPLOY.md` must match what the code actually does.
- Do not ask for secrets in the conversation. For steps that need my accounts, write exact click-by-click instructions in `DEPLOY.md`.

## Order of work

1. Dockerfile, `.dockerignore`, `/ready`, JSON logging, build-time version info.
2. Postgres compatibility run; fix findings.
3. Frontend production config, headers, Monaco decision.
4. Cookie strategy (domain or proxy) implemented and written down.
5. `DEPLOY.md`, env table, final `README.md`.
6. Local container test with a production-like env file.
7. Deploy to staging (or directly to production if there is no staging), run the smoke test, fix, repeat.

## Acceptance check

1. `docker build` and `docker run` locally with a production-like env file: `/health` and `/ready` are OK, migrations ran, and `docker exec … id` shows a non-root user.
2. `/ready` returns 503 when you stop the database.
3. **Production sign-in:** on the real URL, "Login with GitHub" works; the session cookie is `Secure; HttpOnly`; logout and login again work; there are **no CORS or third-party-cookie errors** in the browser console.
4. **Smoke test on production:** paste a public repo → fetched → analyzed → map renders → Explain works → open the editor → save an edit → a foreign-language README is translated → (optional) push to your test repo.
5. Restart the backend service: the working-copy edit from step 4 is still there, and the repo opens (storage option A: files still on disk; option B: files restore on demand).
6. Response headers on the live site include CSP, `nosniff`, referrer policy and HSTS; Monaco loads without CSP violations in the console.
7. Booting with `ENV=production` and a placeholder secret still refuses to start.
8. LangSmith shows production runs tagged `env=production`, `app_version`, `git_sha`, with no secrets.
9. Another person (or a second fresh GitHub account) follows `DEPLOY.md` on a clean staging environment and succeeds without asking you anything.
10. Rolling back to the previous deployment (as documented) works and the database migration state is still consistent.

## Not in this phase

New features. Multi-region deployment, autoscaling, a CDN for repo files. Paid billing. Teams/organizations. Private-repo support. Mobile apps. Translating BodhCode's own UI.

## Paste this to the agent

```text
Read AGENTS.md, then this entire file (17-deploy-and-docs.md).
Implement exactly "Build", obey "Constraints", follow "Order of work".
Do not implement anything under "Not in this phase".
For deployment steps that require my accounts or secrets, write exact instructions in DEPLOY.md and tell me what I must do manually; do not ask me to paste secrets into the chat.
Finish by running the Acceptance check where automatable, report PASS / FAIL / NEEDS MANUAL TEST per item, list commands I must run, then stop.
```
