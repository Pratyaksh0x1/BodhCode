# Phase 11 — The code editor

**Goal.** Open any file of an ingested repo in a VS Code–style workspace: file explorer, tabbed Monaco editor, a changes view with diffs, keyboard shortcuts, and light/dark themes. Edits are saved to a **per-user working copy** — the original repo files are never modified, and nothing is sent to GitHub yet.

## Aapko karna hai (before you paste the prompt)

- [ ] Phase 6 (canvas) aur Phase 7 (editor theme setting) pass ho chuke hain.
- [ ] `git checkout -b phase-11`.
- [ ] `@monaco-editor/react` aur `react-resizable-panels` Phase 1 mein install ho chuke hain; nahi to: `pnpm add @monaco-editor/react react-resizable-panels`.
- [ ] Note: Monaco default mein CDN (jsdelivr) se load hota hai — internet chahiye. Offline/CSP ke liye Phase 17 mein bundling ka option dekhenge.

## Build

### Ingestion update
Bump `INGEST_VERSION` to 2 and extend the extraction allow-list with text files useful for editing: `.md .mdx .css .scss .html .yml .yaml .toml .txt .json .svg` (but **not** `.env*`, key files, lock files, binaries, or anything over the size cap). These files are stored but **not parsed** and do not become graph nodes. A repo ingested at version 1 is re-extracted on next refresh; the editor must handle "files not available — refresh the repo" gracefully.

### Data model (migration)
`WorkingFile`: `id`, `user_id`, `repo_id`, `path`, `content` (text), `is_new` (bool), `is_deleted` (bool), `base_hash` (sha256 of the original content, null for new files), `updated_at`. Unique `(user_id, repo_id, path)`. Only **changed** files have rows.

### File service (`app/files/service.py`)
- `normalize_path(p)`: POSIX, no leading `/`, no `..`, no backslashes, no null bytes, max length 300, no segments that are `.git`; raises `InvalidPath`.
- `read_original(repo, path)`: from the Phase 3 directory, with a resolved-path containment check.
- `read_effective(user, repo, path)`: working copy if present (`is_deleted` → `NotFound`), else original.
- `list_tree(user, repo)`: union of original files and working-copy additions, minus deletions, each entry `{path, status: "unchanged" | "modified" | "added" | "deleted"}`.
- `write_file(user, repo, path, content)`: reject binary (null bytes), > 1,000,000 bytes, invalid UTF-8; if the content equals the original, **delete** the working row (no-op edit); otherwise upsert.
- `revert_file(user, repo, path)`: delete the working row.
- `diff_for(user, repo, path)`: `{path, status, original, modified}` (strings) for the diff view.
- Line endings preserved as provided; no auto-formatting.

### Routes (`app/routes/files.py`, auth + ownership; `{path:path}` for nested paths)
- `GET /repos/{id}/files` → tree with statuses (and `graph_node` flag for files in the graph).
- `GET /repos/{id}/files/{path}` → `{path, content, language_hint, status, size}`.
- `PUT /repos/{id}/files/{path}` `{content}` → saves to the working copy; returns new status. Creating a file = PUT to a new path. Optional `If-Match: <base_hash or hash of current effective content>` header → 412 on mismatch (protects against two tabs overwriting each other).
- `DELETE /repos/{id}/files/{path}` → marks deleted (or removes an added file's row).
- `POST /repos/{id}/files/{path}/revert`.
- `GET /repos/{id}/changes` → list of changed files with statuses.
- `GET /repos/{id}/diff/{path}` → original/modified contents for that path.
- `POST /repos/{id}/files/{path}/rename {new_path}` → implemented as delete + add (keeps it simple).

### Frontend: workspace page `/repos/:id/editor?file=<path>`
Use `react-resizable-panels`; remember sizes in `localStorage` (try/catch).
- **Activity bar** (left, narrow): Explorer, Changes, Search (filename search only), Map (link back to the canvas).
- **Explorer**: lazy-expanding tree (folders collapsed by default; the opened file's ancestors expanded), icons by extension, status decorations (M / A / D color + letter), context menu: New file, Rename, Delete, Revert, "Show in map" (only for graph files).
- **Editor area**: tab bar (open files, dirty dot, close button, middle-click closes, overflow scroll, "close others"), Monaco editor per tab using the `path` prop so each file keeps its own model and undo history. Language inferred from the path. Options: minimap on, word wrap off, font ligatures off, tab size 2, `automaticLayout`.
- **Theme:** `resolveEditorTheme(settings.editor_theme, appTheme)` from Phase 7 → `vs`, `vs-dark`, `hc-black`, `hc-light`; updates live when the user changes the app/editor theme (use `monaco.editor.setTheme`).
- **Saving:** `Ctrl/Cmd+S` saves the active tab with a visible "Saved" status; no autosave in this phase. Unsaved-changes guard on closing a tab and a `beforeunload` warning.
- **Quick open:** `Ctrl/Cmd+P` modal with fuzzy file search (pure scoring function, unit-tested), arrow keys + Enter.
- **Toggle sidebar:** `Ctrl/Cmd+B`. **Toggle bottom panel:** `Ctrl/Cmd+J`.
- **Bottom panel**: tabs "Changes" (list of modified files; clicking opens a **Monaco `DiffEditor`** with original vs. modified, side-by-side/inline toggle) and "Problems" (placeholder text "Diagnostics not available yet").
- **Right panel placeholder** labelled "AI assistant" (disabled, filled in Phase 12).
- **Status bar:** file language, `Ln, Col`, working-copy changes count, repo `owner/name@sha`, "Graph reflects the original commit" notice when there are working-copy changes.
- **From the map:** the Phase 6 side panel's "Open in editor" button is enabled and navigates here with `?file=`.
- Empty and error states: file too large to open (> 1 MB → "Too large to edit"), binary, deleted, repo files unavailable (offer "Refresh repo").

### Tests
Backend: `normalize_path` table (traversal, absolute, backslash, `.git/config`, null byte); read/write/revert round-trip; no-op edit removes the working row; binary and oversize rejected; deleted file 404 on read; `If-Match` 412; ownership isolation (user B never sees user A's changes); `list_tree` merges additions/deletions correctly; containment check blocks symlink tricks.
Frontend (vitest): fuzzy scorer ordering; tab state reducer (open, close, dirty, close others); theme resolution reuse.

## Constraints

- **Original files are read-only.** Only `WorkingFile` rows change; the extracted directory is never written.
- **Every path goes through `normalize_path` and a resolved-containment check** before touching disk or the database.
- Working copy is **per user and per repo**; users never see each other's edits.
- Do not run, import, lint-execute, or build any code from the repository.
- UTF-8 text only. Large or binary files are not editable.
- No LLM calls in this phase. The AI panel is a placeholder.
- The graph is **not** recomputed from the working copy here; the UI says so honestly.
- Monaco models are keyed by `path` so switching tabs does not lose undo history; dispose models when tabs close.

## Order of work

1. Ingestion version bump + re-extraction handling.
2. `WorkingFile` migration, file service, path safety + tests.
3. Routes + ownership/ETag tests.
4. Workspace layout: panels, activity bar, explorer.
5. Monaco tabs, saving, theme sync.
6. Quick open, shortcuts, status bar.
7. Changes panel with `DiffEditor`; revert/rename/delete.
8. Map ↔ editor links; empty/error states.

## Acceptance check

1. From the map, select a file → "Open in editor": the file opens in a tab with syntax highlighting.
2. Edit, press `Ctrl+S`: "Saved"; the explorer shows **M** on the file; reload the page and the edit is still there.
3. Undo history survives switching to another tab and back.
4. Revert the edit manually back to the original text and save: the **M** disappears (no-op edit removed the working row).
5. Create a new file via the explorer: shows **A**; delete a file: shows **D**; Revert restores it.
6. Bottom panel → Changes: clicking a file opens the diff with correct original vs. modified; the inline/side-by-side toggle works.
7. Switch app theme and editor theme in Settings: the editor changes accordingly (Auto follows the app; explicit choices override).
8. `Ctrl+P` finds `compo btn` → `components/Button.tsx` quickly; `Ctrl+B` and `Ctrl+J` toggle panels.
9. Open the same file in two browser tabs, save in one, then save in the other: the second gets a clear conflict message (412), not a silent overwrite.
10. Try `GET /repos/<id>/files/..%2F..%2Fetc%2Fpasswd` and `.git/config`: both rejected.
11. A second user cannot read or change your working copy.
12. Tests, `ruff`, `pnpm lint`, `pnpm build` pass.

## Not in this phase

The AI assistant panel (Phase 12). Running code, a terminal, language servers, linting/diagnostics. Auto-save. Pushing to GitHub (Phase 14). Rebuilding the graph from the working copy. Multi-file search/replace. Git history.

## Paste this to the agent

```text
Read AGENTS.md, then this entire file (11-editor.md).
Implement exactly "Build", obey "Constraints", follow "Order of work".
Do not implement anything under "Not in this phase".
Finish by running the Acceptance check, report PASS / FAIL / NEEDS MANUAL TEST per item, list commands I must run, then stop.
```
