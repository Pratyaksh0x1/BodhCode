# Phase 14 — Push your changes back, in the repo's own language

**Goal.** After editing in BodhCode, a person can turn their working-copy changes into a **pull request** on GitHub — and write the commit message, PR text, issues and comments in *their* language while BodhCode translates them into the repository's language. Nothing is ever sent without a preview and an explicit confirmation.

This phase is the only one that writes to GitHub, so it asks for a bigger GitHub permission and is deliberately careful.

## Aapko karna hai (before you paste the prompt)

- [ ] Phase 9 (translation), Phase 11 (editor) aur Phase 12 (agent) pass ho chuke hain.
- [ ] `git checkout -b phase-14`.
- [ ] **Ek test repo banao jahan aap push kar sako** (apne account par ek chhoti public repo, ya kisi doosri repo ka fork). Asli open-source repo par PR tab hi bhejna jab sab test ho jaye aur aapko PR chahiye ho.
- [ ] GitHub OAuth App mein koi change nahi chahiye (scope runtime par maangi jayegi), par login ke time naya consent screen aayega.
- [ ] Test ke liye ek repo jiski language English se alag ho (Phase 3 mein jo Japanese repo use ki thi), taaki reverse translation check ho sake.

## Build

### Data model (migration)
- `ActionLog`: `id`, `user_id`, `repo_id` (nullable), `action` (`push | issue_create | comment_create | scope_upgrade`), `status` (`previewed | confirmed | succeeded | failed`), `target_url` (nullable), `meta` (JSON, no secrets, no full content), `created_at`.
- `PushPreview`: `id` (random UUID string), `user_id`, `repo_id`, `kind` (`push | issue | comment`), `payload` (JSON of the exact texts and file list to be sent, after translation), `payload_hash`, `expires_at` (30 minutes), `consumed_at` (nullable). **The confirm step sends only what is stored here.**
- `Repo.source_language` and `source_language_confidence` already exist (Phase 9). Add `Repo.push_language_override` (nullable) so a person can correct the detected language.
- `User.token_scopes` (Phase 2) is updated on scope upgrade.

### Scope upgrade (`GET /auth/github/upgrade`)
- Redirects to GitHub authorization with scope `read:user user:email public_repo` (public repos only; private-repo support is out of scope).
- Uses the same Authlib client and state protection as login; on callback, **replace** the stored encrypted token and `token_scopes`, log an `ActionLog(scope_upgrade)`, redirect back to the page the user came from (validated against an allow-list of in-app paths — no open redirect).
- A helper `require_scope(user, "public_repo")` raises a typed error → API returns `403 {"detail": "scope_required", "needed": "public_repo"}`; the frontend responds by explaining and offering the upgrade button.
- Before any write, verify the live token actually has the scope by calling `GET /user` and reading the `X-OAuth-Scopes` response header (the stored value can be stale or revoked).

### Language of the repository
- `get_repo_language(repo)` returns `push_language_override` if set, else `source_language` (Phase 9), else detects now from README + the titles/bodies of the 20 most recent issues/PRs + recent commit messages (`lingua`, confidence threshold 0.6), else `"en"`.
- Settings of the push dialog show "Repository language: Japanese (detected) [change]" — the person can override from the supported catalogue.

### GitHub write client (`app/github/push.py`, extends the client)
Using the Git Data API (no `git` binary):
- `ensure_fork(owner, name)` → if `permissions.push` is true on the upstream repo, use it directly; otherwise create the fork (`POST /repos/{o}/{n}/forks`), then **poll** until it is ready (max 60 s, backoff), return `(fork_owner, fork_name)`. Reuse an existing fork if the user already has one.
- `sync_fork_branch(...)` → if a fork exists but is behind, branch from the **upstream base commit** the user's work was based on: create the commits in the fork via blobs/trees that reference the base tree (fetching the base commit's objects by SHA from upstream is possible once the fork shares history; if the base commit is not found, fail with a clear "sync your fork" message instead of guessing).
- `create_branch(owner, name, branch, from_sha)`.
- `create_blob` (`utf-8` encoding; skip binary/oversize), `create_tree(base_tree, entries)` — for deletions use `sha: null`, `create_commit(message, tree, parents)`, `update_ref`.
- `open_pull_request(upstream_owner, upstream_name, head="fork_owner:branch", base, title, body)`.
- `create_issue(owner, name, title, body)`, `create_comment(owner, name, number, body)`.
- All calls: timeouts, typed errors (reuse Phase 3 mapping, add `PermissionDenied`, `ValidationFailed` with GitHub's message sanitized, `Conflict`), and **no token in any log or exception**.

### Push flow
1. **Preview** — `POST /repos/{id}/push/preview {branch_name, commit_message, pr_title, pr_body, language_override?}`:
   - Requires scope; collects the user's working-copy changes (`modified/added/deleted`); rejects an empty change set, > 100 files, any file > 1 MB, any path failing `normalize_path`, and any file matching secret patterns (see Constraints).
   - Determines `repo_language`. If it differs from `user.preferred_language` (the language the user wrote in), translates `commit_message`, `pr_title`, `pr_body` **from the user's language into the repo language** using the Phase 9 translator with a new `kind="outgoing"` prompt variant (keep code, `#123`, URLs, `@mentions` untouched; conservative, faithful, no embellishment). Also supports "I wrote in English but my account language is Hindi": the preview form has a "**I wrote this in:**" selector defaulting to the user's language.
   - Validates `branch_name` (`^[A-Za-z0-9._/-]{1,100}$`, no `..`, no leading `-`/`/`, not an existing protected name like `main`/`master`).
   - Stores a `PushPreview` and returns `{preview_id, changes: [{path, status}], texts: {commit_message: {original, translated}, pr_title: {...}, pr_body: {...}}, repo_language, target_repo, will_fork: bool}`.
   - `POST /repos/{id}/push/preview/{preview_id}/edit` lets the user **edit the translated texts** (they may know the language); updates the stored payload and hash.
2. **Confirm** — `POST /repos/{id}/push {preview_id, confirm: true}`:
   - Verifies the preview belongs to the user, is unexpired and unconsumed, **and that the working copy still matches the stored change set** (hash of paths+contents); otherwise 409 "changes were modified — preview again".
   - Re-checks scope live, ensures fork, creates branch, blobs, tree, commit, updates ref, opens the PR. Marks the preview consumed **before** the first write to prevent double-submit, and records `ActionLog` transitions.
   - Returns `{pr_url, branch, commit_sha, fork}`. On partial failure returns what exists (e.g. branch created, PR failed) and offers "retry PR creation".
   - Rate limits per user: 5 pushes/hour, 20 issue/comment creations/hour (in-memory or DB-backed counter; 429 with a retry hint).

### Issues and comments
- `POST /repos/{id}/issues/preview {title, body, written_in?}` → same translate-then-preview mechanism; `POST /repos/{id}/issues {preview_id, confirm:true}` creates it.
- `POST /repos/{id}/issues/{n}/comments/preview` and the matching confirm route for replies.
- Optionally link an issue to a PR body ("Fixes #n") — plain text only, no automatic closing logic.

### Frontend
- **"Push changes" button** in the editor's Changes panel (and status bar) → modal wizard:
  1. *Review files*: the list of changes with statuses and per-file diff links; secret-scan warnings block continuing.
  2. *Write it in your language*: branch name (suggested from the commit message), commit message, PR title, PR description; "I wrote this in: [language]".
  3. *Translation preview*: two columns (your text | text that will be sent in {repo language}), each translated field **editable**; a clear banner "This is a machine translation — review before sending."
  4. *Confirm*: shows target `upstream → your fork`, number of files, and a required checkbox "I reviewed the text and files"; then Push.
  5. *Result*: PR link, branch, "View on GitHub".
- If `scope_required`: an explainer step "BodhCode needs permission to create a fork, branch, and pull request on your behalf (public repositories). It will only act when you confirm." with the upgrade button.
- **"Report issue"** and **"Reply"** forms with the same write → preview → confirm flow, available from the Issues/PRs tabs.
- All outgoing actions appear in a small **Activity** list (from `ActionLog`) under Settings.

### Tests (GitHub mocked with `respx`; fake LLM)
- Scope check: missing scope → 403 `scope_required`; live header check overrides a stale stored value.
- Branch name validation table; empty change set rejected; > 100 files / oversize / binary / secret-pattern files rejected.
- Translation: when languages match → no LLM call; when they differ → fields translated once, code/URLs/`#123` preserved (reuse mask tests); editing translated text updates the payload hash.
- Preview expiry; consumed preview cannot be reused (double-submit → 409); working copy changed after preview → 409.
- Fork flow: user has push access (no fork) vs. needs fork (fork created, polled, reused next time); base commit missing → friendly error.
- Git Data call order and payloads: blobs → tree (deletions as `sha: null`) → commit (correct parent) → ref update → PR with `head="fork_owner:branch"`.
- Partial failure reporting; rate limits; ownership isolation of previews.
- Issue and comment preview/confirm flows.
- No token ever appears in logs/exceptions/trace inputs (assert on captured logs).

## Constraints

- **No write to GitHub without (1) a stored preview, (2) the user's explicit confirm, and (3) a live scope check.** Confirm sends only what the preview stored.
- **Machine translation is always shown and editable** before it goes out; never auto-send a translation.
- **Never push secrets:** block files named `.env*`, `*.pem`, `id_rsa*`, `*.key`, `credentials*`, and any content matching common secret patterns (`AKIA…`, `ghp_/gho_/github_pat_`, `gsk_`, `-----BEGIN … PRIVATE KEY-----`, generic `api[_-]?key\s*[:=]\s*\S{16,}`) — show the finding (file + pattern name, never the value) and require removing it.
- Minimum permission: `public_repo` only, requested only when the user chooses to push; no `repo`, no `workflow`, no admin scopes. Do not push files under `.github/workflows/` (GitHub requires another scope) — detect and tell the user.
- Only `github.com` is contacted; redirect targets after OAuth are validated.
- **Idempotency:** consuming the preview happens first; a network retry must not create duplicate branches/PRs (check for an existing branch/PR with the same head before creating).
- No force-pushes, no deleting branches/forks/repos, no merging PRs, no editing existing issues/comments.
- Rate limits and `ActionLog` for every outgoing action; logs contain ids/URLs only, never content or tokens.
- The agent (Phase 12) has **no tool** for pushing — pushing is a human-only action.

## Order of work

1. Migrations, secret scanner (pure) + tests, branch/path validators.
2. Scope upgrade flow + live scope check + tests.
3. `get_repo_language`, outgoing translation prompt variant + tests.
4. GitHub write client + Git Data tests.
5. Preview → edit → confirm endpoints, idempotency, rate limits.
6. Issue and comment flows.
7. Frontend wizard, scope explainer, issue/reply forms, activity list.
8. End-to-end manual test against your own test repo.

## Acceptance check

1. In the editor, make two edits and one new file, click **Push changes** while signed in with the old scope: you see the permission explainer; click upgrade, approve on GitHub, and return to the wizard with your edits intact.
2. Write the commit message and PR text in **English** for a **Japanese** repository: the preview shows the Japanese translation next to your English; edit one word in the Japanese text; continue.
3. Confirm: a fork exists (or the branch is in your test repo), the branch contains exactly your changes (check "Files changed" on GitHub — no extra files), the commit message and PR description are the **Japanese text you approved**, and the PR link opens.
4. Click Push twice quickly (or retry after a network error): only **one** branch/PR is created.
5. Change a file after previewing, then confirm: you get "changes were modified — preview again".
6. Add `API_KEY=abcdef1234567890abcdef` to a file: the wizard blocks and names the file and pattern without echoing the value.
7. Try branch name `main` and `../x`: rejected with a readable message.
8. Report an issue written in English on the Japanese repo: preview, edit, confirm → the issue appears on GitHub in Japanese.
9. Settings → Activity lists the push and issue actions with links; no content or tokens in the entries.
10. Revoke BodhCode's access in GitHub settings, then try to push: you get a clear "permission was revoked — reconnect" message (live scope check), not an obscure 401.
11. Same-language repo (English → English): no translation call occurs and the preview shows a single column.
12. Tests, `ruff`, `pnpm lint`, `pnpm build` pass.

## Not in this phase

Private repositories. Pushing to the upstream's default branch. Merging, closing, or editing existing PRs/issues. Creating repos. GitHub Actions workflow files. Rebase/merge conflict resolution UI. Syncing a fork automatically beyond the checks above. Letting the AI agent push.

## Paste this to the agent

```text
Read AGENTS.md, then this entire file (14-push-to-github.md).
Implement exactly "Build", obey "Constraints", follow "Order of work".
Do not implement anything under "Not in this phase".
Finish by running the Acceptance check, report PASS / FAIL / NEEDS MANUAL TEST per item, list commands I must run, then stop.
```
