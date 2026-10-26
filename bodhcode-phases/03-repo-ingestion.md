# Phase 3 — Paste a repo link, fetch it safely

**Goal.** A signed-in person pastes a GitHub repository link, and the server fetches that repo's source into controlled storage — safely, within limits, and without ever trusting what is inside the download.

Parsing and graphs come later. This phase ends with the files sitting on disk and the repo row saying `fetched`.

## Aapko karna hai (before you paste the prompt)

- [ ] Phase 2 ka acceptance check pass ho chuka hai.
- [ ] `git checkout -b phase-3`.
- [ ] Test ke liye 3 repo links ready rakho: ek chhoti TypeScript repo, ek bahut badi repo (jaise koi famous monorepo, size limit test ke liye), ek Japanese/Chinese README wali repo (Phase 9 ke kaam aayegi).
- [ ] Note: sirf **public** repos supported hain (hum sirf `read:user` scope maangte hain).

## Build

### Settings
Add `DATA_DIR` handling (already exists) plus constants in `app/github/limits.py`: `MAX_REPO_KB = 200_000` (200 MB), `MAX_SOURCE_FILES = 5000`, `MAX_FILE_BYTES = 1_000_000`, `MAX_UNCOMPRESSED_BYTES = 500_000_000`, `INGEST_VERSION = 1`.

### Data model (migration)
`Repo`: `id`, `user_id` (fk, indexed), `owner`, `name`, `branch`, `commit_sha` (nullable until fetched), `status` (`queued | fetching | fetched | analyzing | ready | failed`), `error_code` (nullable), `error_message` (nullable, user-safe text), `file_count`, `default_branch_size_kb`, `ingest_version`, `created_at`, `updated_at`. Unique `(user_id, owner, name)`.

### URL parsing (`app/github/urls.py`, pure)
`parse_repo_url(text) -> RepoRef(owner, name, ref | None)`.
- Accept: `https://github.com/o/r`, `http://`, `www.github.com`, with `.git`, trailing `/`, `/tree/<branch>`, `/tree/<branch>/sub/dir`, `/blob/...`, and shorthand `o/r`.
- Reject: any other host, extra path segments that are not `tree/blob/issues/pull/...`, empty owner/name, and names failing `^[A-Za-z0-9_.-]{1,100}$`. Unicode lookalike hosts must be rejected.
- Raise `InvalidRepoUrl` with a friendly message.

### GitHub client (`app/github/client.py`)
Class `GitHubClient(token)` over `httpx.AsyncClient` (base `https://api.github.com`, timeout 30s). Headers on every call: `Authorization: Bearer <token>`, `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`, a `User-Agent: bodhcode`.
- `get_repo(owner, name)` → metadata (default branch, `size` KB, `private`, `fork`, `permissions`, language).
- `get_branch_sha(owner, name, ref)`.
- `get_tree(owner, name, sha)` (`recursive=1`; if `truncated` is true, record it and continue — the zipball is the source of truth).
- `download_zipball(owner, name, sha, dest_path)` streaming to disk with `follow_redirects=True`; abort and delete the partial file the moment bytes exceed the limit.
- Error mapping to exceptions: 404 → `RepoNotFound` (message: "Repo not found, or it is private — only public repos are supported"), 401 → `TokenInvalid`, 403/429 with `x-ratelimit-remaining: 0` → `RateLimited(reset_at)`, other 4xx/5xx → `GitHubError`.
- The token is passed in via `get_github_token(user)` from Phase 2; the client never logs headers.

### Ingestion (`app/github/ingest.py`)
`async ingest_repo(repo_id)` run as a FastAPI `BackgroundTask`:
1. Set `fetching`. `get_repo`; reject if `private`, or `size` KB over `MAX_REPO_KB` → `failed` with `error_code="too_large"`.
2. Resolve `branch` (given ref or default) and `commit_sha`.
3. Target dir: `DATA_DIR/repos/<owner>/<name>/<commit_sha>/src`. If it exists with a matching `.ingest_version` marker, **reuse it** (shared cache across users; it is public data) and skip download.
4. Else download the zipball to a temp file, then extract safely:
   - Strip the single top-level folder GitHub adds.
   - For each entry: reject absolute paths, any `..` segment, backslashes, symlinks (check `external_attr`), and names with null bytes. Resolve the final path and verify it stays under the target dir.
   - Track total uncompressed bytes; abort over `MAX_UNCOMPRESSED_BYTES` (zip-bomb guard).
   - Allow only: `.ts .tsx .js .jsx .mjs .cjs .mts .cts .d.ts`, `package.json`, `tsconfig*.json`, `jsconfig.json`, and README files (`README*`). Skip files over `MAX_FILE_BYTES`.
   - Skip directories `node_modules`, `.git`, `dist`, `build`, `.next`, `coverage`, `vendor`.
   - If source file count exceeds `MAX_SOURCE_FILES` → `failed`, `error_code="too_many_files"`.
5. Write `.ingest_version` marker, set `file_count`, `status="fetched"`. Wrap everything so any exception ends in `failed` with a **user-safe** message (details only in logs, redacted).
6. DB access from async code goes through `run_in_threadpool` (SQLModel sessions are synchronous).

### Routes (`app/routes/repos.py`, all require `get_current_user`)
- `POST /repos {url}` → parse, upsert the `Repo` for this user (re-pasting the same repo resets it to `queued`), start the background task, return the repo (status `queued`).
- `GET /repos` → the user's repos, newest first.
- `GET /repos/{id}` → one repo (poll target).
- `POST /repos/{id}/refresh` → re-resolve the branch head and re-ingest.
- `DELETE /repos/{id}` → delete the row (not the shared cache directory).
- **Every query filters by `user_id`; another user's id returns 404, never 403.**

### Frontend
- **Home page replaced.** Large input "Paste a GitHub repo link" + Analyze button. Client-side validation mirrors the server's parsing (show the friendly message before sending).
- List of the user's repos as cards: `owner/name`, branch, short sha, status badge (queued / fetching / fetched / failed with the error message), updated time, delete button.
- Poll with `refetchInterval` (2s) only while any repo is `queued` or `fetching`; stop when all are terminal.
- Clicking a `fetched` repo navigates to `/repos/:id` (placeholder page showing status and file count for now).
- Signed-out visitors see the landing hero instead (reuse Phase 2's protection for `/repos/:id`).

### Tests (`respx` for GitHub, temp dirs for disk)
- URL parsing table (≥ 15 cases, valid and hostile).
- Zip with `../evil.txt`, an absolute path, and a symlink entry → none escape the target dir; ingestion fails or skips them.
- Zip bomb: declared uncompressed size over the cap → aborted.
- Oversized `size` → `failed/too_large` without downloading.
- File-count cap, extension allow-list, ignored directories.
- Cache reuse: second ingest of the same sha does not download again.
- Ownership: user B requesting user A's repo id → 404.
- Rate-limit and 404 mapping.

## Constraints

- **The archive is hostile input.** No extraction path is ever built by string concatenation without resolving and checking containment. No file inside the archive is ever executed, imported, or `eval`'d.
- **Nothing is cloned with `git`.** Use the API + zipball only (no shell-outs, no `git clone` of user-supplied URLs).
- Limits are enforced **while downloading and extracting**, not only after.
- Error messages shown to users never contain tokens, internal paths, or stack traces.
- Only `github.com` is ever contacted. Redirects are followed only to GitHub's own download hosts (`codeload.github.com`).
- Storage is local disk under `DATA_DIR`. Do not add S3 or a second database.
- `status` transitions are monotonic per run (`queued → fetching → fetched | failed`); never leave a repo stuck in `fetching` after an exception.

## Order of work

1. `limits.py`, `urls.py` + the URL table tests.
2. `Repo` model + migration.
3. `GitHubClient` + mocked tests (errors, rate limit).
4. Safe extraction function as its own pure-ish unit with the hostile-zip tests.
5. `ingest_repo` + cache logic.
6. Routes with ownership tests.
7. Frontend Home, list, polling.

## Acceptance check

1. Paste the small TypeScript repo URL: card appears as `queued`, becomes `fetching`, then `fetched` with a non-zero file count; no page refresh needed.
2. On disk, `DATA_DIR/repos/<owner>/<name>/<sha>/src` contains only allowed file types and no `node_modules`.
3. Paste the same URL again: status passes through quickly and no second download happens (check logs or `respx` counters in tests).
4. Paste the huge repo: it fails with a clear "too large" message, and no multi-hundred-MB file is left on disk.
5. Paste `https://evil.com/o/r` and `not a url`: friendly inline errors, no request sent.
6. Paste a private or non-existent repo: "not found or private" message.
7. Sign in as a second GitHub account (or tamper the id): `GET /repos/<other user's id>` returns 404.
8. Kill the backend while a repo is `fetching`, restart, and re-paste: it recovers instead of staying stuck (a startup sweep or re-paste resets stale `fetching`).
9. All new tests, `ruff`, `pnpm lint`, `pnpm build` pass.

## Not in this phase

Parsing, graphs, blast radius. README/issue/PR fetching (Phase 9). Private repos and write scopes. Showing file contents (Phase 11). Any LLM call.

## Paste this to the agent

```text
Read AGENTS.md, then this entire file (03-repo-ingestion.md).
Implement exactly "Build", obey "Constraints", follow "Order of work".
Do not implement anything under "Not in this phase".
Finish by running the Acceptance check, report PASS / FAIL / NEEDS MANUAL TEST per item, list commands I must run, then stop.
```
