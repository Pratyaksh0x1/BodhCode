import { memo } from "react";
import { useGraphStore } from "../../store/graphStore";

interface KindDef {
  key: string;
  label: string;
  colorClass: string;
  dashClass?: string;
}

const EDGE_KINDS: KindDef[] = [
  { key: "import", label: "Import", colorClass: "bg-emerald-500 text-emerald-500" },
  { key: "reexport", label: "Re-export", colorClass: "bg-violet-500 text-violet-500" },
  { key: "dynamic", label: "Dynamic", colorClass: "bg-amber-500 text-amber-500", dashClass: "border-dashed" },
  { key: "require", label: "Require", colorClass: "bg-rose-500 text-rose-500", dashClass: "border-dotted" },
];

export const Legend = memo(function Legend() {
  const edgeKindsVisible = useGraphStore((s) => s.edgeKindsVisible);
  const toggleEdgeKind = useGraphStore((s) => s.toggleEdgeKind);
  const hideTypeOnly = useGraphStore((s) => s.hideTypeOnly);
  const toggleHideTypeOnly = useGraphStore((s) => s.toggleHideTypeOnly);

  return (
    <div
      id="canvas-legend"
      aria-label="Canvas Edge Legend and Filters"
      className="bg-white/90 dark:bg-neutral-900/90 backdrop-blur-md border border-neutral-200 dark:border-neutral-800 rounded-xl p-3 shadow-lg flex flex-col gap-2.5 text-xs text-neutral-800 dark:text-neutral-200 select-none transition-colors"
    >
      <div className="flex items-center justify-between gap-3 pb-1 border-b border-neutral-200 dark:border-neutral-800">
        <span className="font-semibold text-[11px] uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
          Edge Kinds
        </span>
      </div>

      {/* Kind Toggles */}
      <div className="flex flex-wrap gap-1.5 items-center">
        {EDGE_KINDS.map((item) => {
          const isVisible = edgeKindsVisible[item.key] ?? true;
          return (
            <button
              key={item.key}
              type="button"
              aria-label={`Toggle ${item.label} edges (currently ${isVisible ? "visible" : "hidden"})`}
              aria-pressed={isVisible}
              onClick={() => toggleEdgeKind(item.key)}
              className={`px-2 py-1 rounded-lg border text-[11px] font-medium flex items-center gap-1.5 transition-all cursor-pointer focus:outline-none focus:ring-2 focus:ring-orange-500/60 ${
                isVisible
                  ? "bg-neutral-100 dark:bg-neutral-800 border-neutral-300 dark:border-neutral-700 text-neutral-900 dark:text-neutral-100 shadow-xs"
                  : "bg-transparent border-transparent opacity-40 text-neutral-400 line-through hover:opacity-60"
              }`}
            >
              <span
                className={`w-2 h-2 rounded-full shrink-0 ${
                  isVisible ? item.colorClass : "bg-neutral-400 dark:bg-neutral-600"
                }`}
              />
              <span>{item.label}</span>
            </button>
          );
        })}
      </div>

      {/* Type-Only Filter Checkbox */}
      <label className="flex items-center gap-2 pt-1 border-t border-neutral-200 dark:border-neutral-800 text-[11px] text-neutral-600 dark:text-neutral-300 cursor-pointer hover:text-neutral-900 dark:hover:text-neutral-100 select-none">
        <input
          id="toggle-hide-type-only"
          type="checkbox"
          checked={hideTypeOnly}
          onChange={toggleHideTypeOnly}
          className="rounded border-neutral-300 dark:border-neutral-700 text-orange-500 focus:ring-orange-500 cursor-pointer"
        />
        <span>Hide type-only imports</span>
      </label>
    </div>
  );
});
