# Security Policy — BodhCode

BodhCode is committed to maintaining the highest security, privacy, and architectural integrity standards across its backend, frontend, and AI subsystems.

---

## 1. Reporting Security Vulnerabilities

We take the security of BodhCode and its users seriously. If you believe you have discovered a vulnerability, please report it responsibly:

- **Do NOT open a public GitHub issue.**
- Submit your report privately via **GitHub Security Advisories**:
  1. Navigate to the repository's **Security** tab.
  2. Click **Report a vulnerability** under Private vulnerability reporting.
  3. Include a detailed description, reproduction steps, proof-of-concept, and the potential impact.
- Alternatively, contact the repository maintainers directly.
- **Commitment**: We acknowledge receipt of vulnerability reports within 48 hours and provide remediation timelines and credit in advisories.

---

## 2. Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| `0.1.x` | :white_check_mark: |
| `< 0.1` | :x:                |

Only the latest active development branch and tagged production releases receive security updates.

---

## 3. Core Architectural Guarantees & Constraints

Every security mechanism in BodhCode is enforced in code and verified by automated continuous integration test suites.

### The Immutable Rule (AST & Graph Isolation)
- **Graph nodes and edges come only from tree-sitter parsing and pure graph math, never from an LLM.**
- The LLM **never** creates, guesses, or "fills in" graph topology, nodes, or edges. It only explains, translates, summarizes, or proposes edits on top of verified structure.

### Pure Modules Stay Pure
- Code in `backend/app/parser/`, blast radius calculations, and dependency graph algorithms has **zero network calls, zero database dependencies, and zero LLM invocations**.
- Outputs are deterministic and sorted.

### Prompt Injection Defense
- Text ingested from GitHub (user repository source code, READMEs, issue comments, pull requests) is treated strictly as **pure untrusted data, never system instructions**.
- Untrusted data is isolated in prompt boundaries and never allowed to override agent instructions.

### Zero-Trust Secret Isolation
- **GitHub OAuth Tokens**:
  - Encrypted at rest using AES-128-CBC (`Fernet`) via `TOKEN_ENCRYPTION_KEY`.
  - Never stored in plain text, never logged, never printed to stdout/stderr.
  - Excluded from LangSmith distributed tracing filters.
  - Never exposed to the browser (API schemas like `UserPublic` omit tokens and scopes).
  - Never injected into raw LLM prompt texts.

### Outbound Network Egress Restrictions
- Backend HTTP clients are strictly restricted to verified external base URLs:
  - `https://api.github.com` (GitHub REST / GraphQL APIs)
  - `https://codeload.github.com` (Repository tarball downloads)
  - `https://api.groq.com` (Fast LLM inference)
  - `https://api.smith.langchain.com` (LangSmith observability, only when enabled)
- Arbitrary user-supplied URLs are never fetched by the server.

### Least Privilege OAuth Scopes
BodhCode requests the minimum necessary permissions from GitHub:
1. **`read:user, user:email` (Default)**:
   - Requested at sign-in.
   - Purpose: Authenticate user identity, retrieve public profile info, and obtain primary verified email for display.
2. **`public_repo` (Elevated, Optional)**:
   - Never requested at sign-in.
   - Requested strictly on-demand when the user chooses to push branches, commits, or open pull requests/issues on public repositories.

---

## 4. User Privacy & "Delete My Data"

Users retain complete sovereignty over their data:
- **What is Stored**:
  - User profile fields (`login`, `github_id`, `name`, `avatar_url`, `email`).
  - Encrypted GitHub OAuth token.
  - User preferences (target language, theme, editor theme, review mode).
  - Working file copies (in-browser code modifications before push).
  - AI write proposals and rollback checkpoints.
  - Sanitized audit logs of outgoing GitHub operations (without secrets or file contents).
- **"Delete My Data" (`POST /auth/disconnect`)**:
  - Accessible directly from **Settings → Privacy & Data**.
  - Requires explicit typed confirmation (`DELETE`).
  - Permanently purges all user records, encrypted tokens, working copies, proposals, rollback checkpoints, and action logs from the database, and clears the session.
  - Shared public repository parse caches are non-personal and remain intact.

---

## 5. Defense-in-Depth & Network Hardening

- **CSRF Protection**: All mutating endpoints (`POST`, `PUT`, `PATCH`, `DELETE`) require the `X-Requested-With: bodhcode` custom header, preventing cross-site browser forged requests without CORS preflight.
- **Strict CORS Policy**: Restricted strictly to `FRONTEND_URL` with explicit credential support. Wildcard origins (`*`) are disallowed.
- **Security Headers**:
  - `X-Content-Type-Options: nosniff`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Cache-Control: no-store` on all authenticated JSON API responses
  - `Content-Security-Policy` restricting script, frame, and connect sources
- **Rate Limiting**:
  - Keyed by `user.id` (or client IP for `/auth/*`), never by token or email.
  - Returns `429 Too Many Requests` with standard `Retry-After` header.
- **Request Body & Resource Limits**:
  - Maximum 1.5 MB default request payload (20 KB for skills / metadata).
  - Background ingestion capped to 3 concurrent tasks with LRU disk cache eviction.
- **Production Boot Guard**:
  - Refuses to start in `ENV=production` if keys are development placeholders, keys are too short, or URLs use insecure `http://`.
