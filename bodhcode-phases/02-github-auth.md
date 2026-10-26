# Phase 2 — GitHub sign-in and sessions

**Goal.** A person signs in with GitHub, stays signed in, can sign out, and cannot reach protected pages while signed out. Their GitHub token is stored so the server can call GitHub for them later, and it never reaches the browser.

GitHub is the **only** sign-in method. There are no passwords, no other providers, and no organizations/teams in BodhCode.

## Aapko karna hai (before you paste the prompt)

- [ ] GitHub OAuth App bana lo (00 mein steps). Callback URL exactly `http://localhost:8000/auth/github/callback`.
- [ ] `backend/.env` mein daalo: `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `TOKEN_ENCRYPTION_KEY` (Fernet key, 00 mein command hai).
- [ ] `git checkout -b phase-2`.
- [ ] Test ke liye ek browser jisme GitHub logged in ho.

## Build

### Settings
Add to `Settings` (required, fail loudly at startup): `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `TOKEN_ENCRYPTION_KEY`. On startup, construct a `Fernet` with the key so a malformed key crashes immediately.

### Data model (first migration)
`User` table: `id` (int pk), `github_id` (int, unique, indexed), `login`, `name` (nullable), `avatar_url`, `email` (nullable), `preferred_language` (default `"en"`), `theme` (default `"dark"`), `encrypted_github_token`, `token_scopes` (string, e.g. `"read:user,user:email"`), `created_at`, `last_login_at`.
Create the Alembic revision with autogenerate, read it, and fix it by hand if needed. Do not use `create_all`.

### Backend modules
- `app/auth/crypto.py`: `encrypt_token(str) -> str`, `decrypt_token(str) -> str` using Fernet. Pure, tested.
- `app/auth/github_oauth.py`: Authlib `OAuth` registry with a `github` client — `authorize_url=https://github.com/login/oauth/authorize`, `access_token_url=https://github.com/login/oauth/access_token`, `api_base_url=https://api.github.com/`, scope `read:user user:email`.
- **Session.** Starlette `SessionMiddleware` with `secret_key=APP_SECRET_KEY`, cookie name `bodhcode_session`, `max_age` 14 days, `same_site="lax"`, `https_only = (ENV == "production")`. The session stores **only** `user_id`. (Authlib also uses this session for its OAuth `state`; that is expected and is the same single session system.)
- **Routes (`app/routes/auth.py`).**
  - `GET /auth/github/login` → `oauth.github.authorize_redirect(request, f"{BACKEND_URL}/auth/github/callback")`.
  - `GET /auth/github/callback` →
    1. `authorize_access_token(request)`; on `OAuthError` redirect to `FRONTEND_URL/?auth_error=denied` (never echo provider error text).
    2. Fetch `GET user`. If `email` is null, fetch `GET user/emails` and take the primary verified one; otherwise leave it null.
    3. Upsert by `github_id` (update login, name, avatar, email, token, scopes, `last_login_at`).
    4. **Clear the old session, then set `user_id`** (prevents session fixation).
    5. Redirect to `FRONTEND_URL`.
  - `GET /auth/me` → public fields only: `id, login, name, avatar_url, email, preferred_language, theme`. 401 when signed out. **Never** returns token fields.
  - `POST /auth/logout` → clears the session, returns 204.
- **Dependencies (`app/auth/deps.py`).** `get_current_user` (reads `user_id` from session, loads user, 401 if missing or user deleted) and `get_optional_user`. All later routes use these.
- **CSRF.** A dependency `require_csrf_header` that rejects any `POST/PUT/PATCH/DELETE` lacking `X-Requested-With: bodhcode` with 403. Apply it at the router level to every router that mutates. (Cross-site pages cannot send this header without a CORS preflight, and CORS only allows `FRONTEND_URL`.)
- **Token usage helper.** `get_github_token(user) -> str` decrypts on demand and is the only place decryption happens. Nothing else touches `encrypted_github_token`.

### Frontend
- `useMe()` hook: `GET /auth/me`, returns `User | null` (401 → `null`, not an error). `staleTime` a few minutes.
- Header right slot: when signed out, a **link** `<a href={VITE_API_URL + "/auth/github/login"}>Login with GitHub</a>` (a real navigation, not `fetch`). When signed in: avatar, login name, a menu with Settings and Logout.
- Logout: `POST /auth/logout`, then clear the query cache and go to `/`.
- `RequireAuth` wrapper for `/settings` and `/repos/:id`: while `useMe` is loading render a neutral skeleton (not the protected page); when `null`, `Navigate` to `/` with a "Sign in to continue" notice. Protected content must never flash.
- If the URL contains `?auth_error=`, show a dismissible banner.

### Tests
- `/auth/me` is 401 without a cookie.
- Encryption round-trips; ciphertext differs from plaintext and starts with Fernet's `gAAAA`.
- Upsert helper: creates then updates the same `github_id` (no duplicate rows).
- Logout clears the session (cookie no longer authenticates).
- CSRF dependency: mutating request without header → 403; with header → passes.
- Callback test with Authlib methods monkeypatched: new session replaces an attacker-supplied pre-login session value.

## Constraints

- **The GitHub token never leaves the server.** Not in any JSON response, not in logs, not in LangSmith traces, not in error messages.
- **Use Authlib.** If a hand-written OAuth state/nonce/token-exchange appears, something has gone wrong.
- **One session system.** Do not add JWT cookies, a second middleware that sets cookies, or any client-side token storage (`localStorage`, `sessionStorage`).
- **Minimum scope.** Only `read:user user:email` now. Write access (`public_repo`) is requested later, in Phase 14, as an explicit upgrade.
- Every query that later touches user data must filter by `user_id` from the session. This phase establishes `get_current_user` as the only source of identity.
- `email` may be null; nothing may assume it exists.

## Order of work

1. Settings additions + startup validation, then `crypto.py` + tests.
2. `User` model + migration; run `alembic upgrade head`.
3. Session middleware, `deps.py`, `/auth/me`, `/auth/logout`, CSRF dependency + tests.
4. OAuth login + callback; verify manually in a browser.
5. Frontend hook, header, `RequireAuth`, logout, error banner.

## Acceptance check

1. Click "Login with GitHub", approve, and land on `/` signed in with your avatar and login visible.
2. In browser devtools → Application → Cookies: `bodhcode_session` exists and is `HttpOnly`. `localStorage` and `sessionStorage` are empty of tokens.
3. Open the `/auth/me` response in the Network tab: no token or scope fields present.
4. In the database, `encrypted_github_token` is a long string starting with `gAAAA`, not a GitHub token (`gho_...`).
5. Reload the page: still signed in. Click Logout: signed out; `/auth/me` is 401.
6. Visit `/settings` while signed out: redirected to `/` with the notice, and the Settings page content never rendered (check the Network tab: no request fired by the page's own data hooks).
7. Sign in twice with the same GitHub account: exactly one `User` row.
8. Start the backend with a malformed `TOKEN_ENCRYPTION_KEY`: it fails at boot naming that variable.
9. Cancel the GitHub authorization screen: you return with the banner, not an error page.
10. `uv run pytest`, `uv run ruff check .`, `pnpm lint`, `pnpm build` pass.

## Not in this phase

Organizations, teams, roles, invitations. Other sign-in providers. Settings page contents (Phase 7). Requesting write scopes. Anything that calls GitHub other than `user` and `user/emails`. Rate limiting (Phase 16).

## Paste this to the agent

```text
Read AGENTS.md, then this entire file (02-github-auth.md).
Implement exactly "Build", obey "Constraints", follow "Order of work".
Do not implement anything under "Not in this phase".
Finish by running the Acceptance check, report PASS / FAIL / NEEDS MANUAL TEST per item, list commands I must run, then stop.
```
