import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { useGraphStore } from "../../store/graphStore";
import { useGraphContext } from "./GraphContext";

export const FolderNode = memo(function FolderNode({
  id,
  data,
}: NodeProps) {
  const graph = useGraphContext();
  const toggleFolder = useGraphStore((s) => s.toggleFolder);
  const blast = useGraphStore((s) => s.blast);

  const name = (data?.name as string) || id;
  const fileCount = (data?.fileCount as number) ?? 1;

  // Check if blast is active and calculate affected files within this folder
  const isBlastActive = Boolean(blast);
  const affectedCount = blast
    ? blast.impacts.filter((imp) => imp.file.startsWith(`${id}/`)).length
    : 0;

  const isDimmed = isBlastActive && affectedCount === 0;

  const handleClick = () => {
    toggleFolder(id, graph);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      toggleFolder(id, graph);
    }
  };

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      title={`Folder: ${id} (${fileCount} files) - Click to expand`}
      className={`w-[200px] h-[52px] box-border px-3 py-2 rounded-xl border flex items-center justify-between cursor-pointer select-none transition-all duration-200 outline-none focus:ring-2 focus:ring-amber-500/70 shadow-sm ${
        isDimmed ? "opacity-35" : "opacity-100"
      } ${
        affectedCount > 0
          ? "bg-rose-50 dark:bg-rose-950/40 border-rose-500 text-rose-900 dark:text-rose-100 ring-2 ring-rose-500/50"
          : "bg-amber-50/90 dark:bg-amber-950/30 border-amber-300 dark:border-amber-700/60 text-amber-950 dark:text-amber-100 hover:border-amber-500 dark:hover:border-amber-400 hover:scale-[1.02]"
      }`}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!w-2 !h-2 !bg-amber-500 dark:!bg-amber-400 !border-white dark:!border-neutral-900"
      />

      <div className="flex items-center gap-2 overflow-hidden mr-1">
        {/* Folder Icon with Chevron indicator */}
        <div className="flex items-center text-amber-600 dark:text-amber-400 shrink-0">
          <svg className="w-4 h-4 fill-current mr-0.5" viewBox="0 0 20 20">
            <path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" />
          </svg>
          <svg className="w-3 h-3 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M9 5l7 7-7 7" />
          </svg>
        </div>

        <div className="overflow-hidden">
          <span className="font-semibold text-xs tracking-tight truncate block">
            {name}
          </span>
          <span className="text-[10px] opacity-70 font-mono block">
            {fileCount} {fileCount === 1 ? "file" : "files"}
          </span>
        </div>
      </div>

      {affectedCount > 0 ? (
        <span
          className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-600 dark:text-rose-300 border border-rose-500/40 shrink-0 animate-pulse"
          title={`${affectedCount} files inside this folder are affected`}
        >
          {affectedCount} affected
        </span>
      ) : (
        <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-500/15 text-amber-700 dark:text-amber-300 border border-amber-500/30 shrink-0 font-mono">
          +{fileCount}
        </span>
      )}

      <Handle
        type="source"
        position={Position.Right}
        className="!w-2 !h-2 !bg-amber-500 dark:!bg-amber-400 !border-white dark:!border-neutral-900"
      />
    </div>
  );
});
