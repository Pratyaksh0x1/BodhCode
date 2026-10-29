import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { useGraphStore } from "../../store/graphStore";
import type { GraphNode } from "../../lib/repos";

export const FileNode = memo(function FileNode({
  id,
  data,
}: NodeProps) {
  const selectedFileId = useGraphStore((s) => s.selectedFileId);
  const blast = useGraphStore((s) => s.blast);
  const select = useGraphStore((s) => s.select);

  const name = (data?.name as string) || id;
  const folder = (data?.folder as string) || "";
  const fanIn = (data?.fanIn as number) ?? 0;
  const fanOut = (data?.fanOut as number) ?? 0;
  const graphNode = data?.node as GraphNode | undefined;
  const inCycle = graphNode?.flags?.includes("in_cycle") ?? false;
  const hasParseError = graphNode?.flags?.includes("parse_error") ?? false;

  const isSelected = selectedFileId === id;
  const isBlastActive = Boolean(blast);
  const isBlastTarget = blast?.file === id;
  const blastImpact = blast?.impacts?.find((imp) => imp.file === id);
  const isBlastAffected = Boolean(blastImpact);
  const blastDepth = blastImpact?.depth;

  const isDimmed = isBlastActive && !isBlastTarget && !isBlastAffected;

  // Determine border & background styling based on blast and selection states
  let colorClasses =
    "bg-white dark:bg-neutral-900/90 border-neutral-200 dark:border-neutral-700/80 text-neutral-800 dark:text-neutral-100 hover:border-orange-500/60 dark:hover:border-orange-500/60";

  if (isBlastTarget) {
    colorClasses =
      "bg-orange-500/15 dark:bg-orange-500/20 border-orange-500 text-orange-950 dark:text-orange-100 ring-2 ring-orange-500 shadow-[0_0_18px_rgba(249,115,22,0.45)]";
  } else if (isBlastAffected) {
    if (blastDepth === 1) {
      colorClasses =
        "bg-rose-500/20 dark:bg-rose-950/50 border-rose-500 text-rose-950 dark:text-rose-100 ring-2 ring-rose-500/80 shadow-[0_0_12px_rgba(244,63,94,0.35)]";
    } else if (blastDepth === 2) {
      colorClasses =
        "bg-orange-500/15 dark:bg-orange-950/40 border-orange-500 text-orange-950 dark:text-orange-100 ring-1 ring-orange-500/70";
    } else if (blastDepth === 3) {
      colorClasses =
        "bg-amber-500/15 dark:bg-amber-950/40 border-amber-500 text-amber-950 dark:text-amber-100 ring-1 ring-amber-500/50";
    } else {
      colorClasses =
        "bg-yellow-500/10 dark:bg-yellow-950/30 border-yellow-500/80 text-yellow-950 dark:text-yellow-100";
    }
  } else if (isSelected) {
    colorClasses =
      "bg-orange-50/50 dark:bg-neutral-900 border-orange-500 text-neutral-900 dark:text-neutral-100 ring-2 ring-orange-500 shadow-[0_0_14px_rgba(249,115,22,0.3)]";
  }

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    select(id);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      select(id);
    }
  };

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      title={`${id}\nIn: ${fanIn} | Out: ${fanOut}${inCycle ? " (Circular dependency)" : ""}`}
      className={`w-[240px] h-[56px] box-border px-3 py-2 rounded-xl border flex flex-col justify-between cursor-pointer select-none transition-all duration-150 outline-none focus:ring-2 focus:ring-orange-500/70 shadow-sm ${
        isDimmed ? "opacity-25" : "opacity-100"
      } ${colorClasses}`}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!w-2 !h-2 !bg-sky-500 dark:!bg-sky-400 !border-white dark:!border-neutral-900"
      />

      {/* Top row: Filename + Indicators */}
      <div className="flex items-center justify-between gap-1.5 overflow-hidden">
        <div className="flex items-center gap-1.5 overflow-hidden">
          {/* File icon */}
          <svg
            className="w-3.5 h-3.5 text-neutral-400 dark:text-neutral-500 shrink-0"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>

          <span className="font-semibold text-xs tracking-tight truncate block">
            {name}
          </span>
        </div>

        {/* Status badges */}
        <div className="flex items-center gap-1 shrink-0">
          {isBlastTarget && (
            <span className="px-1 py-0.2 rounded text-[9px] font-bold bg-orange-500 text-white font-mono">
              TARGET
            </span>
          )}

          {isBlastAffected && !isBlastTarget && (
            <span
              className={`px-1 py-0.2 rounded text-[9px] font-bold font-mono ${
                blastDepth === 1
                  ? "bg-rose-500 text-white"
                  : blastDepth === 2
                  ? "bg-orange-500 text-white"
                  : "bg-amber-500 text-neutral-900"
              }`}
            >
              d={blastDepth}
            </span>
          )}

          {inCycle && (
            <span
              className="text-amber-500 dark:text-amber-400 text-xs font-bold"
              title="Circular dependency warning"
            >
              ⚠️
            </span>
          )}

          {hasParseError && (
            <span
              className="text-rose-500 text-xs font-bold"
              title="Tree-sitter parse error in this file"
            >
              ⛔
            </span>
          )}
        </div>
      </div>

      {/* Bottom row: Folder path + fan-in / fan-out badges */}
      <div className="flex items-center justify-between text-[10px] text-neutral-400 dark:text-neutral-500 font-mono">
        <span className="truncate max-w-[130px]" title={folder || "root"}>
          {folder || "."}
        </span>

        <div className="flex items-center gap-1.5 shrink-0">
          <span title={`Fan-in (imported by ${fanIn} files)`} className="text-sky-600 dark:text-sky-400">
            &darr;{fanIn}
          </span>
          <span title={`Fan-out (imports ${fanOut} files)`} className="text-violet-600 dark:text-violet-400">
            &uarr;{fanOut}
          </span>
        </div>
      </div>

      <Handle
        type="source"
        position={Position.Right}
        className="!w-2 !h-2 !bg-sky-500 dark:!bg-sky-400 !border-white dark:!border-neutral-900"
      />
    </div>
  );
});
