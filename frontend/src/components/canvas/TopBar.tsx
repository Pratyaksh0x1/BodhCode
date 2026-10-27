import { memo } from "react";
import { canExpandAll } from "../../lib/graphView";
import { useGraphStore } from "../../store/graphStore";
import { useGraphContext } from "./GraphContext";

export const TopBar = memo(function TopBar() {
  const graph = useGraphContext();
  const expandAll = useGraphStore((s) => s.expandAll);
  const collapseAll = useGraphStore((s) => s.collapseAll);

  const canExpand = canExpandAll(graph);

  return (
    <div
      id="canvas-top-bar"
      className="bg-white/90 dark:bg-neutral-900/90 backdrop-blur-md border border-neutral-200 dark:border-neutral-800 rounded-2xl px-4 py-2.5 shadow-md flex flex-wrap items-center justify-between gap-3 text-xs text-neutral-800 dark:text-neutral-200 select-none transition-colors"
    >
      {/* Left: Repo info & Commit */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5 font-semibold text-sm">
          <span className="text-neutral-500 dark:text-neutral-400">
            {graph.repo.owner}/
          </span>
          <span className="text-orange-500 font-bold">{graph.repo.name}</span>
        </div>

        {graph.repo.commit_sha && (
          <span
            className="px-2 py-0.5 rounded-md font-mono text-[11px] bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-300 border border-neutral-200 dark:border-neutral-700"
            title={`Commit ${graph.repo.commit_sha}`}
          >
            @{graph.repo.commit_sha.slice(0, 7)}
          </span>
        )}
      </div>

      {/* Middle: Graph Stats Badges */}
      <div className="flex items-center gap-2 font-mono text-[11px]">
        <span
          className="px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800/80 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700"
          title="Total analyzed source files"
        >
          <strong>{graph.stats.files}</strong> files
        </span>
        <span
          className="px-2 py-0.5 rounded-full bg-sky-100 dark:bg-sky-950/60 text-sky-700 dark:text-sky-300 border border-sky-200 dark:border-sky-800"
          title="Dependency import edges"
        >
          <strong>{graph.stats.edges}</strong> edges
        </span>
        <span
          className="px-2 py-0.5 rounded-full bg-indigo-100 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800"
          title="External npm packages referenced"
        >
          <strong>{graph.stats.external_packages}</strong> pkgs
        </span>
        {graph.stats.cycles > 0 && (
          <span
            className="px-2 py-0.5 rounded-full bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800 font-bold"
            title="Circular dependency loops detected"
          >
            ⚠️ <strong>{graph.stats.cycles}</strong> cycles
          </span>
        )}
      </div>

      {/* Right: Expand/Collapse All Controls */}
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => expandAll(graph)}
          disabled={!canExpand}
          title={
            canExpand
              ? "Expand all folders into files"
              : "Expand all is disabled because it would exceed the 600 visible nodes cap"
          }
          className="px-3 py-1 rounded-lg border text-xs font-medium transition-all cursor-pointer focus:outline-none focus:ring-2 focus:ring-orange-500/60 disabled:opacity-40 disabled:cursor-not-allowed bg-neutral-100 dark:bg-neutral-800 border-neutral-300 dark:border-neutral-700 hover:bg-neutral-200 dark:hover:bg-neutral-700 text-neutral-800 dark:text-neutral-100"
        >
          Expand all
        </button>

        <button
          type="button"
          onClick={collapseAll}
          title="Collapse all folders"
          className="px-3 py-1 rounded-lg border text-xs font-medium transition-all cursor-pointer focus:outline-none focus:ring-2 focus:ring-orange-500/60 bg-neutral-100 dark:bg-neutral-800 border-neutral-300 dark:border-neutral-700 hover:bg-neutral-200 dark:hover:bg-neutral-700 text-neutral-800 dark:text-neutral-100"
        >
          Collapse all
        </button>
      </div>
    </div>
  );
});
