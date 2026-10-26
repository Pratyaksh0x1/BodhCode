# Phase 6 — The interactive map

**Goal.** A person opens an analyzed repo and sees its dependency graph on a zoomable canvas: folders they can expand into files, edges colored by kind, a side panel for the selected file, a "show blast radius" button that lights up everything affected, and a search box.

The data comes only from `GET /repos/{id}/graph` and `GET /repos/{id}/blast`. The canvas never invents nodes or edges.

## Aapko karna hai (before you paste the prompt)

- [ ] Phase 5 acceptance pass; kam se kam do repos `ready` hon (ek chhoti, ek 300–1000 files wali).
- [ ] `git checkout -b phase-6`.
- [ ] Browser mein light aur dark dono dekhne ke liye OS theme badalna aana chahiye.
- [ ] Packages Phase 1 mein install ho chuke hain (`@xyflow/react`, `dagre`, `vitest`). Agar nahi: `pnpm add @xyflow/react dagre && pnpm add -D @types/dagre vitest`.

## Build

### State (`src/store/graphStore.ts`, zustand)
`expandedFolders: Set<string>`, `selectedFileId: string | null`, `blast: {file, impacts} | null`, `search: string`, `edgeKindsVisible: Record<kind, boolean>`, `hideTypeOnly: boolean`. Actions: `toggleFolder`, `expandPathTo(fileId)`, `select`, `clearBlast`, `setSearch`. Server data (graph, blast) stays in react-query, **not** in zustand.

### Pure view logic (`src/lib/graphView.ts`, unit-tested with vitest)
Given `GraphDoc` and `expandedFolders`:
- `representativeOf(fileId)`: the id of the nearest **collapsed** ancestor folder of that file, or the file itself if every ancestor is expanded.
- `visibleNodes()`: unique representatives, typed `folder` or `file`.
- `visibleEdges()`: for each real edge, map both endpoints to representatives; drop edges whose endpoints map to the same node; merge duplicates into one edge carrying `{kinds: Set, count, typeOnlyOnly: boolean}`.
- `initialExpanded(graph)`: expand nothing but the top level; if the repo has a single top-level folder (such as `src`), expand it automatically.
- `ancestorsOf(fileId)` for revealing search results.
No React imports in this file.

### Layout (`src/lib/layout.ts`)
`layoutWithDagre(nodes, edges, {direction: "LR"})` returning positioned nodes. Node sizes: folders 200×52, files 240×56. Memoize on the **sorted list of visible ids + visible edge ids** so toggling unrelated state does not re-layout. Run layout in `useMemo` (or a worker if it exceeds ~150 ms on the large fixture).

### Components
- `RepoCanvas` — `ReactFlow` with `nodeTypes`/`edgeTypes` defined **outside** the component (or memoized), `onlyRenderVisibleElements`, `fitView` on first render, `minZoom`/`maxZoom`, `colorMode` following the app theme (`"dark" | "light"`), `MiniMap`, `Controls`, `Background`. Import `@xyflow/react/dist/style.css` once.
- `FolderNode` — name, file count, chevron; click toggles expansion; shows an **impact badge** ("N affected") when it contains blast-radius files.
- `FileNode` — file name + muted folder path, small badges for fan-in/fan-out, a warning icon if it is in a cycle, and a dim/highlight state.
- `KindEdge` — color by `kind` (import, reexport, dynamic, require) with a legend; `dynamic` dashed; `type-only` drawn thinner. Edge colors must work in light and dark and must **not** rely on color alone (also differ by dash/width).
- `Legend` — edge kinds with toggles to hide/show a kind, plus "Hide type-only".
- `SidePanel` (right, resizable) for the selected file:
  - path, size, exports list;
  - **Imported by** (dependents) and **Imports** (dependencies), each entry clickable to select/pan to it (expands ancestors if hidden);
  - **External packages** list;
  - flags (parse error, unresolved imports count);
  - **Show blast radius** button → `GET /blast`; shows total and a depth-grouped list (depth 1, 2, 3…); **Clear** button;
  - **Open in editor** button, disabled with a tooltip "Available in a later phase".
- `SearchBox` (top-left, `Ctrl+K` focuses it): substring/fuzzy match over node ids; arrow keys + Enter selects; selecting calls `expandPathTo`, then centers the node with React Flow's `fitView({nodes:[{id}], duration: 400})`.
- `TopBar` — repo name, commit sha (short), stats, "Expand all" (disabled above the node cap), "Collapse all".

### Blast radius highlighting
When `blast` is set: nodes in `impacts` get a color scale by depth (1 strongest); the selected node gets a distinct ring; every other node is dimmed (reduced opacity, not hidden). Collapsed folders containing affected files show the badge instead of expanding. Clearing the blast restores normal styling. Escape clears blast, then selection.

### Large graphs
- Node cap: `MAX_VISIBLE_NODES = 600`. If expanding would exceed it, show a non-blocking banner "Too many nodes — collapse some folders" and refuse that expansion (and disable "Expand all").
- Do not render edges between invisible nodes (the aggregation above guarantees this).

### Page wiring (`/repos/:id`)
Handles states: not analyzed (button), `analyzing` (progress + polling), `failed` (message + retry), `ready` (canvas). Tabs scaffold: **Map** (this phase), README / Issues / PRs (later; disabled "Coming soon" tabs are fine).

### Tests (vitest)
- `representativeOf`/`visibleEdges` on a hand-built graph: collapsed folder aggregation, duplicate merging, same-representative edges dropped, kinds union.
- `initialExpanded` for single-top-folder repos.
- Cap logic refuses expansion over 600.
- Layout memoization key is stable for the same visible set.

## Constraints

- **No node or edge that is not in the API response.** Aggregated folder edges are derived by the pure function above and say so (tooltip: "N imports across folders").
- `nodeTypes`/`edgeTypes` must not be recreated each render (React Flow warns and re-mounts).
- Server state in react-query, UI state in zustand. Do not store the whole graph in zustand.
- All colors via Tailwind tokens/CSS variables that change with the `dark` class — no hard-coded light-only colors.
- Keyboard accessible: nodes focusable, Enter selects, Esc clears, side-panel controls are real buttons with labels.
- No LLM calls and no editor in this phase.
- Do not mutate the graph response object; copy before deriving.

## Order of work

1. `graphView.ts` + vitest (the hard logic first).
2. Store, then `RepoCanvas` with plain nodes and dagre layout; confirm a small repo renders.
3. Folder expand/collapse; edge aggregation.
4. Custom nodes/edges, legend toggles, minimap, controls.
5. Side panel and navigation between related files.
6. Blast highlight and clear.
7. Search + shortcuts.
8. Node cap, empty/error states, polish for dark and light.

## Acceptance check

1. Open a small `ready` repo: the graph appears, fitted to the screen, with no console errors or React Flow warnings.
2. Collapsed folders show file counts; clicking one expands it into files and the layout updates smoothly; collapsing restores the aggregated edges.
3. Click a file: the side panel lists its imports and importers; clicking an entry in the list pans to and selects that file (even if its folder was collapsed — it expands).
4. "Show blast radius" on a widely imported file: all affected nodes are highlighted by depth, others dimmed, collapsed folders show an "N affected" badge, and the total matches `GET /blast`'s `total`. Escape clears it.
5. Toggle each edge kind in the legend: those edges disappear and reappear. "Hide type-only" removes type-only edges.
6. `Ctrl+K`, type part of a filename deep in the tree, press Enter: the folders along its path expand and the canvas centers on it.
7. On the 300–1000-file repo, pan/zoom stays smooth, and trying to expand beyond 600 visible nodes shows the banner and refuses.
8. Switch OS theme between light and dark: the canvas, nodes, edges, minimap and panel all follow with readable contrast.
9. Tab through the page with the keyboard: you can reach the search, legend toggles, nodes, and side-panel buttons.
10. `pnpm test`, `pnpm lint`, `pnpm build` pass.

## Not in this phase

AI explanations or chat (Phase 10). The editor and "Open in editor" behavior (Phase 11). README/Issues/PR tabs (Phase 9). Editing the graph. Saving node positions. Exporting images.

## Paste this to the agent

```text
Read AGENTS.md, then this entire file (06-canvas.md).
Implement exactly "Build", obey "Constraints", follow "Order of work".
Do not implement anything under "Not in this phase".
Finish by running the Acceptance check, report PASS / FAIL / NEEDS MANUAL TEST per item, list commands I must run, then stop.
```
