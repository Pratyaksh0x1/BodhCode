# BodhCode — Retrofit guide (phases pehle se bane hain)

`BODHCODE-CHANGES.md` mein jo changes hain, unhe ab **bani hui codebase** par lagana hai. Yeh file batati hai kis order mein, kaun sa prompt, aur har step ke baad kya check karna hai.

Agent ko do cheezein attach karo: `AGENTS.md` aur `BODHCODE-CHANGES.md`. Har prompt batata hai ki us file ke kaun se hisse lagane hain.

**Maine ek decision aapki taraf se le liya hai:** Changes file ke Section B ka #8 (GitHub token) mein **option (a)** liya hai, yaani token abhi jaisa encrypted store hota rahe. Naya app bana hua hai aur yeh sabse kam risk wala hai. Baad mein badalna ho to Step 10 ke baad alag se kar sakte ho.

**Update: Phase 17 (deploy) abhi execute nahi hua hai.** Isliye retrofit ko **deploy se pehle** karo. Deploy sabse aakhir mein, final code ke saath ek hi baar. Production mein koi data nahi hai, to purane graphs ko rebuild karna sirf aapke local DB ke liye hai, aur staging/production wale checks Phase 17 mein honge. Retrofit ke baad deploy ke liye kya dhyan rakhna hai, woh is file ke aakhir mein "Phase 17 ke liye additions" mein hai.

---

## Step 0 — Taiyari (sirf aap, agent nahi)

1. `git checkout main && git pull && git checkout -b retrofit/00-baseline`.
2. **Database ka backup:** SQLite ho to `cp backend/bodhcode.db backend/bodhcode.db.bak`. Postgres ho to `pg_dump` chalao.
3. Baseline tests: `uv run pytest`, `uv run ruff check .`, `pnpm lint`, `pnpm test`, `pnpm build`. Sab green hone chahiye. Jo fail ho woh pehle theek karo, warna baad mein pata nahi chalega ki retrofit ne kya toda.
4. **Baseline snapshot** (parser badalne par "edges byte-identical" check ke liye): 3 repos chuno (ek chhoti, ek barrel files wali, ek 300+ files wali). Har ek ka `GET /repos/{id}/graph` save karo `baseline/<name>.graph.json` mein. Agar CLI abhi nahi hai to saved JSON hi kaafi hai. Is folder ko commit mat karo.
5. `git commit --allow-empty -m "retrofit baseline"`, phir har step ke liye nayi branch: `retrofit/01-parser`, `retrofit/02-adapters`, ...

**Har step ka rule:** pehle branch, phir prompt, phir acceptance check, phir PR, CodeRabbit padho, merge. Tab agla step. Ek saath do step mat karo.

---

## Sabhi prompts ka common hissa

Har prompt ke shuru mein yeh paste karo (ek baar bata do to baad mein sirf "Common rules apply" likh sakte ho):

```text
Context: BodhCode is already fully built (all phases from bodhcode-phases/ exist in this codebase). We are retrofitting changes from the attached BODHCODE-CHANGES.md.
Common rules:
1. Read AGENTS.md and the relevant code first. Tell me what already exists and what differs from what the change file assumes BEFORE you edit. Adapt to the real code; do not recreate what exists.
2. Every schema change is a new, reversible Alembic migration with a data step for existing rows. Never edit old migrations.
3. Do not break existing tests. Update tests whose behaviour was deliberately changed and say which.
4. Keep AGENTS.md rules: graph from parser only, LLM never invents structure, secrets never logged/traced, pure parser package stays pure.
5. Implement only the listed items. Do not start the next step.
6. Finish with: files changed, migrations added, commands I must run, then PASS / FAIL / NEEDS MANUAL TEST for each acceptance item.
```

---

## Step 1 — Parser: coverage, accounting, CLI, hashes, CommonJS exports

**Branch:** `retrofit/01-parser`  **Pure Python, UI nahi badlega.**

**Prompt:**
```text
[Common rules above]
From BODHCODE-CHANGES.md implement: section "04-parser-extract-resolve.md" (all P1 items and the two P2 items), the graph-JSON additions listed under "05-graph-and-blast-radius.md" for `loc`, `content_hash`, `coverage` (leave `role`, `framework`, `routes`, `insights` as empty/null placeholders for now), and the single `walk(g, file, direction, depth)` function with `blast_radius` and `dependencies` as thin wrappers (default depth 2, `max_depth=None` still means unlimited so existing callers keep working).
Specific requirements:
- Bump PARSER_VERSION and graph `version`. Old stored graphs become invalid and are rebuilt on next analyze (existing behaviour); add a one-off script `python -m app.scripts.reanalyze_all` that re-runs analysis for repos already in the DB, resumable and rate-limit friendly.
- Edge list for existing fixtures must stay byte-identical (golden test). New fields are additive only.
- Add the CLI `python -m app.parser.cli <dir> [--out graph.json]`.
- Coverage: percent = internal_resolved / (internal_resolved + unresolved); null when the denominator is 0.
```

**Aapko karna hai:** `uv run python -m app.scripts.reanalyze_all` (agent ke commands ke hisaab se) apne local DB ki ek repo par chalao. Production abhi hai nahi, isliye wahan kuch nahi karna.

**Acceptance:**
1. `uv run pytest backend/tests/parser` green, golden edge-list tests pass.
2. Baseline repos par CLI chalao: **edges baseline JSON ke edges se byte-identical** (sirf naye fields extra).
3. `found = parsed + skipped` print hota hai aur har skip ka reason hai.
4. Ek imported file rename karo, parser dobara chalao: **exactly ek** unresolved import, reason ke saath.
5. Ek CommonJS repo (`module.exports`, `exports.x`) par exports ke naam aate hain.
6. Coverage ka percent naam se aata hai; zero-import repo par `null`, "100%" nahi.

**Rollback:** `git revert` branch merge, aur `alembic downgrade -1` agar migration thi.

---

## Step 2 — Framework adapters, roles, routes, taxonomy

**Branch:** `retrofit/02-adapters`  **Depends:** Step 1.

**Prompt:**
```text
[Common rules above]
From BODHCODE-CHANGES.md implement the new phase "05b-framework-adapters-and-roles.md" in full, on top of the parser from step 1:
- app/parser/adapters/ with the adapter interface and a fixed-order registry (nextjs, nestjs, express, react, generic; first match wins; no match -> generic roles and an empty route table).
- shared/taxonomy.json read by both backend and frontend (concrete category names, fixed order).
- Fill graph JSON fields: framework, routes[], node.role, node.role_source="convention" (or "generic"). Bump graph/parser version again if the schema changed.
- Routes are exact or absent: emit only when method and the full pattern are both recoverable from parsed syntax without inference.
- Express: roles only, no routes.
- Expose routes through GET /repos/{id}/routes (ownership enforced) and a read-only tool function for later use.
- Tests: fixtures for a Next.js app-router repo, a Next.js pages-router repo, a NestJS repo (including a controller with a non-literal path, which must emit NO route), an Express repo, a React repo, and a repo matching nothing. Add a test that framework names appear only inside app/parser/adapters/ and that adapters emit only roles present in taxonomy.json.
Frontend in this step: only a minimal routes table on the repo page and the rail categories rendered from taxonomy.json (full canvas redesign is step 5).
```

**Aapko karna hai:** Test ke liye ek Next.js repo, ek NestJS repo, ek Express repo aur ek aisi repo jo kisi se match na kare, taiyar rakho.

**Acceptance:**
1. Next.js repo: rail mein Page routes / API endpoints / Server actions aur sahi ginti.
2. NestJS repo: Controllers / Services / Modules, route table mein method aur poora pattern.
3. Table se **3 routes haath se code ke saath match karo** (method aur path dono).
4. Jo repo kisi se match na kare wo render hoti hai, roles generic, route table khaali (galat nahi).
5. Express repo jo pehle khaali graph deti thi, ab asli edges deti hai, aur coverage ka denominator asli hai.
6. `grep -ri nextjs backend/app/parser` sirf `adapters/` mein milta hai.

---

## Step 3 — Insights (bina model ke)

**Branch:** `retrofit/03-insights`  **Depends:** Step 2 (roles chahiye).

**Prompt:**
```text
[Common rules above]
From BODHCODE-CHANGES.md implement the new phase "06b-insights.md": pure functions in app/parser/insights.py (files nothing imports, import cycles, unusually high fan-in, overly long files), four fixed sentence strings, iterative cycle detection, orphan exclusion for framework-reached roles (pages, routes, layouts, middleware, config, tests), thresholds as documented constants. Store insights in the graph JSON `insights[]`. Frontend: a collapsed Insights panel (never the first thing shown), ordering with "files nothing imports" first, zero network requests when opened. No model calls anywhere in this step.
```

**Acceptance:**
1. Jis file ko koi import nahi karta woh insights mein aati hai.
2. Koi page/route jise koi import nahi karta woh **nahi** aata.
3. Ek asli cycle haath se chalkar confirm karo.
4. Panel kholne par network tab mein koi request nahi.
5. Shuru mein panel collapsed hai.

---

## Step 4 — Ingestion lifecycle: ek repo ek analysis, stages, stale, live progress

**Branch:** `retrofit/04-lifecycle`  **Depends:** Step 1.

**Prompt:**
```text
[Common rules above]
From BODHCODE-CHANGES.md implement section B items 1, 4 and 5 and everything listed under "03-repo-ingestion.md":
- One analysis per repo per user: POST /repos on an already-known repo returns the existing row (HTTP 200) and the UI navigates to it. Add a separate deliberate "Re-analyze" action/route. Update the frontend flow and any tests that assumed re-paste resets the row. Include a data migration that checks existing rows for duplicates and reports them (do not silently delete).
- Named stages (queued, fetching, selecting, parsing, storing, ready, failed) with stage, stage_message, failed_stage, updated_at heartbeat; failures record which stage and why.
- Stale runs: unfinished runs whose updated_at is older than N minutes (config, default 5) show as "stale" on the dashboard.
- GET /repos/{id}/freshness comparing remote HEAD to the stored commit sha.
- Replace polling with SSE GET /repos/{id}/events: ownership enforced, publishes only {stage, message}. In-process asyncio pub/sub; use Postgres LISTEN/NOTIFY when running with more than one worker or on Postgres. Keep polling only as a fallback when the stream drops.
- Replace "fail above 5000 files" with structural selection (seed from entry points and walk outward, or keep whole directories; never largest-N-by-size). Record what was left out in coverage. Keep hard failures only for repo size, zip safety and total-bytes limits.
Add the headers and heartbeat that make SSE proxy-safe (no buffering, comment lines every 15 seconds). Real-host testing happens later in Phase 17, so do not add any hosting-specific code now.
```

**Acceptance:**
1. Ek repo do baar paste karo: dashboard mein **ek hi row**, doosri baar existing analysis khulti hai.
2. Stages naam ke saath aate hain (spinner nahi) aur map tak pahunchte hain.
3. Doosre browser tab mein run ke dauran stage bina refresh update hota hai.
4. Nonexistent repo: failed, message saaf, row "parsing" par atki nahi.
5. Run ke beech backend process kill karke restart karo: kuch minute baad row "stale" dikhti hai.
6. 5000+ file wali repo ab fail nahi hoti, partial banti hai aur coverage bataata hai kya chhoda.
7. SSE response mein proxy-safe headers hain (`Cache-Control: no-cache`, `X-Accel-Buffering: no`) aur har 15 second par heartbeat aata hai. Asli host par test Phase 17 mein hoga.

---

## Step 5 — Canvas aur panes (sabse bada frontend change)

**Branch:** `retrofit/05-canvas`  **Depends:** Steps 1–4. Isko **3 PR** mein todo: 5a, 5b, 5c. Har ek ka alag prompt.

### 5a — Folding aur panels
```text
[Common rules above]
From BODHCODE-CHANGES.md section "06-canvas.md" implement ONLY: the auto-folding rule (deepest-first merging of directories with fewer than 2 files, raise the threshold until under ~24 nodes, each pass computed fresh; pure function with vitest), folded nodes opening into a single bordered panel with header (name, file count, fan-in/out) and file rows (with "N more"), edges terminating on rows, header click to close, node height = fan-in, width from label, shortest-unique labels, deterministic layout, refit on open that only zooms out and is computed from the post-change expansion state. Remove the old initialExpanded/loose-node expansion logic. Do not touch the shell, rail, pane or banner yet.
```
**Acceptance (numbers report karo):** 1) nodes ~24 se kam aur lagbhag har 10 files par 1 node; 2) har node mein ek se zyada file; 3) har edge existing node par khatam; 4) folded node click karne par panel khulta hai aur header click par band; 5) graph canvas bharta hai, labels bina zoom ke padhne layak.

### 5b — Shell, rail, detail pane
```text
[Common rules above]
From BODHCODE-CHANGES.md section "06-canvas.md" implement ONLY: the fixed 3-column shell (left rail, map, right detail pane; pane is never a modal/drawer), left rail categories from shared/taxonomy.json with colour, name and count, rail click that DIMS non-matching nodes (not hide) with per-panel match counts, the detail pane resting state (repo summary: name, framework, counts, most depended-on files, files nothing imports, count of unidentified files), the Structure and Explanation tabs with the open tab persisting across selection changes, clickable paths, two-way hover highlighting, and zero network requests on selection. Move Ask/chat into a mode of the whole right pane (item B6) instead of a drawer.
```
**Acceptance:** 1) kuch click kiye bina pane repo ka summary dikhata hai; 2) file select karne par network tab mein **zero** naye requests; 3) pane mein "7" likha hai to 7 paths listed hain; 4) Explanation tab khol kar doosri file select karo, tab wahi rehta hai; 5) rail category click par baaki dim hote hain aur panel ke match counts ka jod rail ki ginti ke barabar hai; 6) Ask toggle ON karne par pura pane badalta hai, OFF par jo selected tha wapas aata hai.

### 5c — Coverage banner, blast depth, Settings status
```text
[Common rules above]
From BODHCODE-CHANGES.md implement: the coverage banner on the map (collapses to one line that still shows the percent; open by default under 95%; never shows 100% when the denominator is zero), blast radius default depth 2 with "Show deeper" (3, 4, all) and dependency chain sharing the same walk, instant (no spinner) results, and the "System status" section in Settings/footer backed by GET /meta/status (llm_configured, tracing_enabled, model) from item "08-llm-layer-and-tracing.md".
```
**Acceptance:** 1) awkward repo (aliases ya nested app) par banner 95% se kam figure ke saath aata hai; 2) banner collapse karo, figure line mein dikhta rahta hai; 3) Blast radius default 2 levels, "Show deeper" se badhta hai; 4) dependency chain aur blast radius ek hi walk se aate hain (test mein same results).

---

## Step 6 — LLM layer: model pin, status, traced cache helper

**Branch:** `retrofit/06-llm`  **Depends:** Step 5c (status endpoint) ya akela bhi chal sakta hai.

**Prompt:**
```text
[Common rules above]
From BODHCODE-CHANGES.md implement the items under "08-llm-layer-and-tracing.md" and "09-translation.md" and section B item 2: exact pinned model name included in every cache key and in trace metadata; GET /meta/status; a helper cached_traced_call that performs the cache read INSIDE the traced function so a cache hit is recorded as a run with zero tokens and no model call. Switch translation to the helper. Existing cache rows keep working or are cleanly invalidated by the new key format (say which). Add tests for: cache hit creates a traced run with zero tokens; changing the model name invalidates only that model's entries; tracing disabled -> zero outbound LangSmith calls.
```
**Acceptance:** 1) ek translation do baar chalao: LangSmith mein **dono runs** hain, doosre mein tokens = 0; 2) `LANGSMITH_TRACING=false` par calls chalte hain aur Settings mein "tracing off" dikhta hai; 3) model naam badalo: purani cache entries us naye model ke liye use nahi hoti.

---

## Step 7 — Explain, folder explain, roles, staleness, chat rules

**Branch:** `retrofit/07-explain`  **Depends:** Steps 2, 5b, 6.

**Prompt:**
```text
[Common rules above]
From BODHCODE-CHANGES.md implement everything under "10-grounded-explain-and-chat.md" and section B items 2, 3 and 6:
- Folder explain: separate prompt and route.
- Role classification for files no adapter identified; allow-list of non-structural roles only (service, repository, model, util, config, component, hook); anything else becomes generic; stored with role_source="model".
- Cache key = content_hash(file) + neighbour-list hash + model + prompt_version + language. Cache read inside the traced call.
- Output formatting: prompt permits only inline code, bullets, bold, no headings; frontend renders those three and turns every repo path in the prose into a link that moves the map.
- Explanation stays in the pane when selection moves away and returns.
- Staleness using stored content_hash and /freshness; offer re-analyze.
- Verification set: explain checks mentions against the neighbours handed to the model; chat checks against the union of tool-result paths; whole-graph check remains a second layer.
- Chat: every final answer must have at least one tool call; if none, retry once forcing a tool call, else refuse.
- Add the prompt rule that the model never talks about its own tools, APIs or plumbing.
Tests with a fake LLM for each of the above, including a role the model must not be allowed to return (page/route/controller).
```
**Acceptance:** 1) Explain: paragraph neighbours ke naam ke saath, naam par click se map hilta hai; 2) rendered text mein koi stray backtick, asterisk ya hash nahi; 3) dobara click: instant, LangSmith mein run **zero tokens** ke saath; 4) folded folder explain: jawab folder ke baare mein hai, ek file ka summary nahi; 5) repo mein commit push karo, reload, badli hui file par Explain: "explanation purani hai" aur re-analyze ka option; 6) jis file ko koi adapter nahi pehchanta uska role sensible hai aur routable nahi; 7) chat ka har answer kam se kam ek tool call ke saath aata hai.

---

## Step 8 — Agent tools aur safety tests

**Branch:** `retrofit/08-agent`  **Depends:** Steps 2, 7.

**Prompt:**
```text
[Common rules above]
From BODHCODE-CHANGES.md implement everything under "12-agent-tools-and-review.md": add read tools list_files_by_role(role) and get_routes(); merge blast_radius/list_dependencies into one walk(direction, depth) tool while keeping older tool names working for existing skills (alias them and log a deprecation note); add the test that no tool accepts a repo id or user id as an argument (the repo comes only from ctx); add the test that the rest of the app keeps working when the LLM provider is unreachable. Check existing default skills in backend/app/skills/defaults/ still pass validation against the updated tool list and update any that reference renamed tools.
```
**Acceptance:** 1) "which files are controllers?" `list_files_by_role` use karta hai; 2) "what routes exist?" `get_routes` use karta hai aur sirf wahi routes batata hai jo table mein hain; 3) purani skills (jaise `/explain-file`) ab bhi chalti hain; 4) Groq key galat karke map, pane, blast radius, editor sab chalte hain.

---

## Step 9 — Evals aur CI

**Branch:** `retrofit/09-evals`  **Depends:** Steps 1–8.

**Prompt:**
```text
[Common rules above]
From BODHCODE-CHANGES.md implement everything under "15-evals.md" and "16-ci-and-security.md": live invented_paths evaluator logged as feedback on real explain/chat traces (deterministic set membership against the exact set shown to the model); role-accuracy suite over held-out convention-labelled files (at least 30, only roles the classifier may return); old explain prompt moved to evals/prompts/ and compared with the current one as two LangSmith experiments, with a clear note that the judge is a model; agent evaluators looked_before_answering, no_plumbing_talk, hedge_vs_look; Suite A additions (coverage numbers, rename -> exactly one unresolved); CI test that framework names appear only under app/parser/adapters/. Update evals/thresholds.json with sensible initial thresholds from a first run and report the numbers.
```
**Acceptance:** 1) invented-path check real explanations par score deta hai; 2) ek nakli filename splice karo, woh pakda jaata hai; 3) role accuracy percentage aata hai (30+ files); 4) do prompt versions LangSmith mein side by side, score aur kitna fark; 5) CI green.

---

## Step 10 — Landing page

**Branch:** `retrofit/10-landing`  **Depends:** sab pichhle (claims sach hone chahiye).

**Prompt:**
```text
[Common rules above]
From BODHCODE-CHANGES.md implement the new phase "16b-landing-page.md" in full. Only describe features that exist in this codebase right now; list what the product deliberately does not do in the final section. Carry the pasted repo URL through GitHub sign-in using a validated `next` parameter (reuse the existing redirect allow-list). Use the product's existing colour tokens and components only; no screenshots, no testimonials, no pricing.
```
**Acceptance:** signed-out page bina video ke samjha deta hai; hero mein URL paste karke sign-in ke baad seedha analysis tak pahunchte ho; theme toggle par sab sahi; phone width par horizontal scroll nahi.

---

## Step 11 — Aakhri safai

**Branch:** `retrofit/11-final`

**Prompt:**
```text
[Common rules above]
Final pass after the retrofit: update README.md and bodhcode-phases/00-START-HERE.md to match the code as it is now, and add a section titled "Retrofit additions" to bodhcode-phases/17-deploy-and-docs.md listing everything deployment must account for: GET /meta/status, SSE progress and its proxy requirements, shared/taxonomy.json and the Docker/frontend build-context requirement, Postgres LISTEN/NOTIFY when more than one worker runs, new env vars if any, and the migrations. DEPLOY.md does not exist yet (Phase 17 creates it), so do not create it. Remove any leftover dead code: old loose-node expansion, polling-only paths that are no longer needed, unused graph fields. Run the whole acceptance list of steps 1-10 once more where automatable and report PASS/FAIL/NEEDS MANUAL TEST.
```

**Aapko karna hai (Phase 17 se pehle):**
1. Local DB par `reanalyze_all` chalao (purane graphs naye schema par rebuild hote hain).
2. Pehle ke 3 baseline repos dobara dekho: edges wahi hain, naye fields (coverage, roles, routes) aaye hain.
3. Phir `bodhcode-phases/17-deploy-and-docs.md` execute karo, neeche ke "Phase 17 ke liye additions" ke saath.

---

## Agar kuch atak jaye

```text
This error happens in retrofit step N. Full traceback and the command I ran: <paste>. Find the root cause first, explain it in simple Hinglish, then fix it with the smallest change, and add a test so it does not return. Do not touch anything outside step N.
```

## Chhote nuskhe

- Agar kisi step mein agent bole "yeh pehle se hai", to uska diff dekho, aur jo hai usse Acceptance check se verify karo. Bas "haan hai" par bharosa mat karo.
- Migrations ke baad hamesha `alembic upgrade head` ek khali DB par bhi chalao, aur `alembic downgrade -1` ek baar test karo.
- Step 5 ko kabhi ek PR mein mat karo. Teen alag PR mein hi review lagega.

---

## Phase 17 (deploy) ke liye additions

Retrofit ke baad Phase 17 ka spec waise hi rehta hai, bas yeh cheezein ab bhi dhyan mein rakhni hain. Phase 17 ka prompt dene se pehle yeh paste karo:

```text
Before starting, read the "Retrofit additions" section of bodhcode-phases/17-deploy-and-docs.md and the "Phase 17 ke liye additions" list I give below. Treat them as part of the Build section.
1. Live progress uses SSE (GET /repos/{id}/events). The host and any proxy in front of the API must not buffer it: verify X-Accel-Buffering/Cache-Control headers survive, check the host's idle timeout against the 15-second heartbeat, and document it in DEPLOY.md. If the host cannot stream, say so and keep the polling fallback.
2. shared/taxonomy.json lives outside backend/ and frontend/. The backend Dockerfile build context must include it (build from the repo root, or copy it in), and the frontend host must be able to read it (enable "include files outside the root directory", or add a build step that copies it and a test that both copies are identical). Make the choice and test both builds.
3. If WEB_CONCURRENCY is greater than 1, or the database is Postgres, progress events must use Postgres LISTEN/NOTIFY, not the in-process broadcaster. Verify with two workers.
4. GET /meta/status must be reachable by the signed-in UI and must not leak secrets. Confirm tracing and model name appear correctly in production.
5. Freshness checks call GitHub for the remote HEAD. Confirm they respect rate limits and use the user's token, and that they cannot loop.
6. The landing page hero passes the pasted repo URL through sign-in with a validated `next` parameter. Add the production frontend origin to the redirect allow-list and test it on the real domain.
7. Run the full migration chain on a fresh Postgres database, then run the whole test suite against Postgres once.
8. There is no existing production data, so no reanalyze_all is needed on the server. Make sure the first deploy runs migrations on an empty database.
```

Baaki Phase 17 ka sab kuch (Dockerfile, `/ready`, cookies ka same-domain ya proxy decision, production OAuth App, naye secrets, `DEPLOY.md`, README) bina badlaav ke wahi karna hai. Retrofit ka koi bhi step 17 ke Acceptance check ko nahi badalta.
