# Phase 4 — The parser: what each file imports and exports

**Goal.** Given the source files of a repository, produce — deterministically, with no network, no database and no LLM — a list of **facts** per file (imports, re-exports, dynamic imports, `require` calls, exported names) and a **resolver** that turns each import into a real file in the repo, an external package, or "unresolved".

This is the foundation of BodhCode's one rule: the map is built from real code analysis, never from AI. Everything in this phase lives in `app/parser/` and must stay pure.

## Aapko karna hai (before you paste the prompt)

- [ ] Phase 3 acceptance pass ho chuka hai aur kam se kam ek repo `fetched` hai.
- [ ] `git checkout -b phase-4`.
- [ ] 2–3 real TypeScript repos ka link taiyar rakho jinke imports aap jaante ho (manual comparison ke liye).
- [ ] Kuch download nahi karna; `tree-sitter` packages Phase 1 mein install ho chuke hain.

## Build

### Data types (`app/parser/types.py`)
Frozen dataclasses (or pydantic models) — immutable, hashable, JSON-serializable:
- `ImportKind = Literal["import", "reexport", "dynamic", "require"]`
- `ImportRef`: `specifier: str`, `kind: ImportKind`, `line: int`, `type_only: bool`
- `FileFacts`: `path: str` (repo-relative, POSIX), `imports: tuple[ImportRef, ...]`, `exports: tuple[str, ...]` (sorted, de-duplicated), `has_default_export: bool`, `unresolved_dynamic: int` (non-literal `import(x)` / `require(x)` count), `flags: tuple[str, ...]` (e.g. `"parse_error"`, `"skipped_large"`, `"skipped_unsupported"`)
- `Resolution`: `kind: Literal["file", "external", "builtin", "unresolved"]`, `target: str | None` (repo path for `file`), `package: str | None` (for `external`)

### Extraction (`app/parser/extract.py`)
`extract_file(path: str, source: bytes) -> FileFacts`.
- Language by extension: `.ts .mts .cts .d.ts` → TypeScript grammar; `.tsx` → TSX grammar; `.js .jsx .mjs .cjs` → JavaScript grammar (it handles JSX). Build each `Language`/`Parser` once (module-level, lazily). Use the py-tree-sitter API of the installed version (`Language(tree_sitter_typescript.language_typescript())` etc.) — check the installed version's docs and do not guess method names.
- Walk the tree **iteratively with an explicit stack** (no recursion; minified or generated files can be very deep).
- Detect and record:
  - `import x from "a"`, `import {a} from "a"`, `import * as n from "a"`, side-effect `import "a"` → kind `import`.
  - `import type {…} from "a"` and `import {type X} from "a"` (all specifiers type-only) → `type_only=True`.
  - `export {a} from "b"`, `export * from "b"`, `export * as ns from "b"` → kind `reexport` (also `type_only` for `export type … from`).
  - `import("literal")` → kind `dynamic`. Non-literal argument (variable, template with `${}`) → increment `unresolved_dynamic`, **no edge**.
  - `require("literal")` → kind `require`; non-literal → `unresolved_dynamic`. Only treat `require` as a call to the bare identifier `require`.
  - TypeScript `import x = require("a")` → kind `require`.
  - Exports: `export function/class/const/let/var/enum/interface/type/namespace X`, `export {a, b as c}` (record the exported name `c`), `export default …` (set `has_default_export`, do not add a name), `export * from` does **not** add names.
- String literal values: read the string fragment content, not the quotes; ignore strings containing escapes you cannot decode safely (count as non-literal).
- `root_node.has_error` → still return everything found and add flag `parse_error`.
- Files over 1 MB → `skipped_large`, empty facts. Unknown extension → `skipped_unsupported`.
- Output ordering: imports sorted by `(line, specifier, kind)`. Calling twice gives identical results.

### tsconfig handling (`app/parser/tsconfig.py`)
- `parse_jsonc(text) -> dict`: a small, string-aware stripper for `//` and `/* */` comments and trailing commas (must not break on `//` inside strings like `"https://x"`).
- `load_tsconfigs(files: Mapping[str, bytes]) -> TsConfigIndex`: find every `tsconfig*.json`/`jsconfig.json` (prefer `tsconfig.json`), parse, and resolve `extends` for **relative** paths only, depth ≤ 5, cycle-safe. Keep `baseUrl` and `paths`, normalized relative to the repo root.
- `TsConfigIndex.for_file(path)`: the nearest tsconfig in the file's directory chain (monorepo-friendly); `None` if none.
- Invalid JSON never raises out of this module; it logs-free returns "no config" for that file and records a warning in the index.

### Resolution (`app/parser/resolve.py`)
`resolve(from_path: str, spec: str, all_files: frozenset[str], tsconfig: TsConfig | None) -> Resolution`.
Order of rules:
1. `node:`-prefixed specifier or a name in the Node builtin list (`fs`, `path`, `http`, …) → `builtin`.
2. Relative (`./`, `../`, `.`, `..`): join with the importing file's directory and normalize (POSIX, no leaving the repo root → `unresolved`).
3. Alias: if `tsconfig.paths` has a matching pattern (support a single `*` wildcard; longest/most specific prefix wins; try each target in order), then `baseUrl`-relative bare specifiers.
4. Anything else bare → `external`, with `package` normalized: `@scope/pkg/sub` → `@scope/pkg`, `lodash/fp` → `lodash`.
For a candidate path, try in this exact order:
 a. exact path if it exists;
 b. **ESM extension mapping**: if it ends in `.js` try `.ts` then `.tsx`; `.jsx` → `.tsx`; `.mjs` → `.mts`; `.cjs` → `.cts`;
 c. append each of `.ts .tsx .d.ts .js .jsx .mjs .cjs .json`;
 d. directory index: `<dir>/index` + each of the extensions above.
If nothing matches → `unresolved`. Resolution results are deterministic and independent of dict ordering.
Workspace packages (monorepo packages referenced by name) are treated as `external` for now.

### Orchestrator (`app/parser/analyze.py`)
`analyze_repo_files(files: Mapping[str, bytes]) -> list[FileFacts + resolved imports]` — pure; takes already-loaded bytes, returns facts with each import annotated by its `Resolution`. A separate thin function in `app/github/ingest.py` or a service module reads the extracted directory into that mapping (not part of the pure package).

### Fixtures and tests (`backend/tests/parser/` + `tests/fixtures/`)
Create tiny fixture repos as directories, each with an `expected.json`:
1. `basic_imports` — static, named, namespace, side-effect, type-only.
2. `reexports` — barrel file with `export *`, `export * as`, `export {a} from`.
3. `dynamic_and_require` — literal and non-literal `import()` / `require()`.
4. `aliases` — `tsconfig.json` with `baseUrl` + `paths` (`@/*`), including comments and trailing commas in the JSON.
5. `esm_extensions` — `import "./a.js"` where only `a.ts` exists.
6. `index_files` — directory imports resolving to `index.ts`.
7. `externals` — scoped and deep package imports, `node:` builtins.
8. `monorepo` — two tsconfigs, nearest-config selection, `extends`.
9. `broken_syntax` — a file with a syntax error still yields partial facts + `parse_error`.
Tests assert **exact** expected facts and resolutions, determinism (run twice, equal), and that no function in `app/parser/` imports `httpx`, `sqlmodel`, `groq`, `os.environ` or opens network sockets (a test greps the package imports).

## Constraints

- **Pure package.** Nothing under `app/parser/` imports from `app.db`, `app.github`, `app.ai`, performs I/O, reads env, or uses randomness or the current time.
- **No LLM, no heuristics that guess.** If a specifier cannot be resolved by the rules above, it is `unresolved` — never "probably this file".
- Never `eval`, `exec`, `import`, or run anything from the analyzed repository.
- Deterministic output: sorted collections, no reliance on set iteration order, no timestamps.
- Resilient: one malformed file must never abort the analysis of the others; every per-file failure becomes a flag.
- Performance target: 5,000 typical files under ~30 seconds on a laptop; no per-file re-creation of parsers.
- Node builtin list is a constant in code, not fetched from anywhere.

## Order of work

1. `types.py`, then fixtures 1–3 and `extract.py` until they pass.
2. Exports extraction + fixture 9.
3. `tsconfig.py` (JSONC stripper first, with its own tests).
4. `resolve.py` against fixtures 4–8.
5. `analyze.py` orchestration and the purity test.
6. A small benchmark script (not a test) printing files/second on a fixture of 2,000 generated files.

## Acceptance check

1. `uv run pytest backend/tests/parser` passes, including the determinism and purity tests.
2. Run `extract_file` manually on a file containing every import form in "Build": the facts list each one with the right `kind`, line, and `type_only`.
3. A file with `import(someVariable)` yields `unresolved_dynamic = 1` and **no** edge.
4. `import "./util.js"` with only `util.ts` present resolves to `util.ts`.
5. `@/components/Button` resolves through a `paths` alias to the right file; with the alias removed it becomes `external` — not a wrong file.
6. A JSONC `tsconfig.json` with comments and trailing commas parses; `//` inside a string value survives.
7. `import "@scope/pkg/deep/path"` resolves to `external`, package `@scope/pkg`.
8. On one real fetched repo from Phase 3, run the orchestrator in a Python shell: spot-check 5 files' imports against the source by eye — they match.
9. The benchmark prints a rate that meets the target.
10. `ruff` clean.

## Not in this phase

Building the graph, nodes/edges JSON, blast radius, cycles (Phase 5). Any API route. Storing results in the database. Python, Go, or any language other than TS/JS. Resolving workspace package names to local folders. Following `package.json` `exports`/`main`.

## Paste this to the agent

```text
Read AGENTS.md, then this entire file (04-parser-extract-resolve.md).
Implement exactly "Build", obey "Constraints", follow "Order of work".
Do not implement anything under "Not in this phase".
Finish by running the Acceptance check, report PASS / FAIL / NEEDS MANUAL TEST per item, list commands I must run, then stop.
```
