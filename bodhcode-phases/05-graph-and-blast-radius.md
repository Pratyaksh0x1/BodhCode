# Phase 5 — The graph, blast radius, and the graph API

**Goal.** Turn the parser's facts into one canonical graph (nodes = files, edges = dependencies), do the "what breaks if I change this file?" arithmetic over it, store the result per repository commit, and expose it through a small API.

Still no LLM. The graph produced here is the **only** source of truth for every later feature.

## Aapko karna hai (before you paste the prompt)

- [ ] Phase 4 acceptance pass.
- [ ] `git checkout -b phase-5`.
- [ ] Ek repo jise aap achhe se jaante ho (jismein ek file ko 5–10 files import karti ho) manual verification ke liye select karo.

## Build

### Graph schema (`app/parser/graph.py`, pure)
`build_graph(facts: list[AnalyzedFile], repo_meta: RepoMeta) -> GraphDoc` where `GraphDoc` serializes to exactly this JSON (versioned):

```
{
  "version": 1,
  "repo": {"owner": "...", "name": "...", "commit_sha": "..."},
  "nodes": [
    {"id": "src/a.ts", "name": "a.ts", "folder": "src", "size": 1234,
     "exports": ["foo", "bar"], "has_default_export": true,
     "external_deps": ["react", "zod"], "unresolved_count": 0,
     "unresolved_dynamic": 0, "flags": []}
  ],
  "edges": [
    {"id": "src/a.ts>src/b.ts#import", "source": "src/a.ts", "target": "src/b.ts",
     "kind": "import", "type_only": false, "count": 1}
  ],
  "folders": [{"id": "src", "parent": "", "file_count": 12}],
  "stats": {"files": 0, "edges": 0, "external_packages": 0, "cycles": 0, "unresolved": 0}
}
```
Rules:
- Node `id` is the repo-relative POSIX path. Only files in the repo become nodes.
- Edge direction is **source imports target**.
- One edge per `(source, target, kind, type_only)`; repeated imports increase `count`.
- Self-imports produce no edge. External/builtin/unresolved imports produce **no edge** (they feed `external_deps` and `unresolved_count`).
- `folders` lists every ancestor directory of every file, with `parent` (`""` for the top level) and recursive `file_count`.
- All lists sorted: nodes by `id`, edges by `(source, target, kind, type_only)`, folders by `id`. Output is byte-identical for identical input.
- `parser_version` constant `PARSER_VERSION = 1` lives next to the schema.

### Graph math (`app/parser/blast.py`, pure, uses `networkx`)
Build a `networkx.DiGraph` from the `GraphDoc` once (`to_digraph(doc, include_type_only=True)`), then:
- `blast_radius(g, file, *, include_type_only=True, max_depth=None) -> list[Impact]` — every file that **transitively imports** `file` (BFS over reversed edges). `Impact = {file, depth, via}` where `via` is the neighbour one step closer to the changed file on the BFS tree. Sorted by `(depth, file)`. The changed file itself is not included.
- `dependencies(g, file, *, depth=1) -> list[Impact]` — what it imports (forward BFS).
- `dependents(g, file) -> list[str]` — direct importers.
- `find_cycles(g) -> list[list[str]]` — strongly connected components with more than one node, plus single nodes with self-loops; each cycle sorted internally, the list sorted by first element.
- `degree_stats(g) -> dict[file, {fan_in, fan_out}]`.
- Unknown `file` → raise `NodeNotFound` (never return an empty list for a typo).
- Re-export (barrel) edges count as dependency edges, so changing a re-exported file correctly reaches its consumers through the barrel.

### Persistence (migration)
`RepoGraph`: `id`, `repo_id` (fk, unique with `commit_sha`), `commit_sha`, `parser_version`, `graph_json` (JSON/Text), `node_count`, `edge_count`, `created_at`. A graph is **valid** only if its `parser_version` equals the current `PARSER_VERSION` and its `commit_sha` equals the repo's current `commit_sha`.

### Analysis job
`async analyze_repo(repo_id)` (BackgroundTask): set `analyzing` → load files from the Phase 3 directory into memory (cap total size) → `analyze_repo_files` → `build_graph` → save `RepoGraph` → set `ready` and `stats` counters. Any exception → `failed` with `error_code="analyze_failed"` and a safe message. If a valid graph already exists, skip and set `ready`.

### Routes (all require auth and filter by `user_id`; unknown/foreign repo → 404)
- `POST /repos/{id}/analyze` → starts the job (409 if status is not `fetched`/`ready`/`failed`-retryable), returns the repo.
- `GET /repos/{id}/graph` → the stored `graph_json`. 409 with `{"detail": "not_ready"}` if no valid graph. Supports `ETag` = `sha + parser_version` and answers `304` when `If-None-Match` matches. Set `Cache-Control: private, max-age=0, must-revalidate`.
- `GET /repos/{id}/blast?file=<path>&include_type_only=true&max_depth=` → `{file, total, impacts: [{file, depth, via}]}`.
- `GET /repos/{id}/deps?file=<path>&depth=1` → dependencies + dependents lists.
- `GET /repos/{id}/cycles` → list of cycles.
- `file` must be a node id in this graph; otherwise 404 `{"detail": "file_not_in_graph"}`. Reject paths containing `..` or backslashes before lookup.
- Cache the parsed `DiGraph` in memory with an LRU (max ~20 entries keyed by `(repo_id, commit_sha, parser_version)`), so repeated blast calls do not re-parse the JSON.

### Frontend (minimal; the canvas is Phase 6)
- On `/repos/:id`, show status, "Analyze" button when status is `fetched`, polling while `analyzing`, and — when `ready` — the stats (files, edges, external packages, cycles) as small cards.

### Tests
- Fixture-based golden tests: `build_graph` output equals an `expected_graph.json` per fixture (reuse Phase 4 fixtures plus `cycle` and `barrel` fixtures).
- Determinism: building twice yields identical bytes; shuffling the input order yields identical bytes.
- Blast radius: exact `(file, depth, via)` lists on a hand-drawn diamond graph; a leaf with no importers returns `[]`; `include_type_only=False` removes impacts that exist only through type-only edges; `max_depth` truncates.
- Cycles: a→b→c→a detected; self-import ignored; no false positives on a diamond.
- API tests: ownership isolation, 409 before analysis, `ETag`/304, unknown file 404, traversal strings rejected.
- Purity test from Phase 4 extended to `graph.py` and `blast.py`.

## Constraints

- **Graph math is arithmetic over the stored graph.** No LLM call, no network, no database access inside `graph.py` or `blast.py`.
- The stored JSON is the contract with the frontend and with every AI tool later. Change it only by bumping `version`/`PARSER_VERSION` and handling old rows (they become invalid and are rebuilt).
- Edge direction is fixed (importer → imported). Every function documents which way it traverses.
- Limits: refuse to build a graph with more than 20,000 edges or 5,000 nodes (`failed`, `graph_too_large`) — protects memory.
- No endpoint returns file contents in this phase.
- All endpoints validate that the repo belongs to the signed-in user before reading anything.

## Order of work

1. Graph schema + builder with golden fixtures.
2. `blast.py` + tests.
3. `RepoGraph` model, migration, analysis job.
4. Routes + ownership/ETag tests.
5. Frontend stats cards + analyze button.
6. Manual verification on a real repo.

## Acceptance check

1. On a fetched repo, click Analyze: status goes `analyzing` → `ready`; the stats cards show non-zero files and edges.
2. `GET /repos/<id>/graph` returns JSON matching the schema above; calling it twice with `If-None-Match` returns `304`.
3. Pick a file you know many files import. `GET /repos/<id>/blast?file=<that file>` lists those importers at depth 1 and their importers at depth 2, and **every** importer you can find by searching the repo for the import appears.
4. A file nobody imports returns `total: 0`.
5. `GET /repos/<id>/blast?file=nope.ts` → 404 `file_not_in_graph`; `?file=../x` → 4xx.
6. `GET /repos/<id>/cycles` lists a known cycle if the repo has one (use the `cycle` fixture if not).
7. Analyze the same repo twice: the second run is instant (cached valid graph) and the JSON is byte-identical.
8. User B cannot read user A's graph (404).
9. `uv run pytest`, `ruff`, `pnpm lint`, `pnpm build` pass.

## Not in this phase

The visual map (Phase 6). Folder-level aggregation (frontend concern). Any AI explanation. Graph of the user's edited working copy (later phases show a "graph reflects original commit" notice). Languages other than TS/JS.

## Paste this to the agent

```text
Read AGENTS.md, then this entire file (05-graph-and-blast-radius.md).
Implement exactly "Build", obey "Constraints", follow "Order of work".
Do not implement anything under "Not in this phase".
Finish by running the Acceptance check, report PASS / FAIL / NEEDS MANUAL TEST per item, list commands I must run, then stop.
```
