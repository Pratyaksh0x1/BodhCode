import { memo } from "react";
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type EdgeProps,
} from "@xyflow/react";
import { useGraphStore } from "../../store/graphStore";

export const KindEdge = memo(function KindEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  source,
  target,
}: EdgeProps) {
  const blast = useGraphStore((s) => s.blast);

  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const rawKinds = data?.kinds;
  const kinds = Array.isArray(rawKinds)
    ? rawKinds
    : rawKinds instanceof Set
    ? Array.from(rawKinds)
    : [];

  const count = (data?.count as number) ?? 1;
  const typeOnlyOnly = Boolean(data?.typeOnlyOnly ?? data?.typeOnly ?? false);

  // Determine primary kind & visual differences (color, dash, stroke width)
  const isDynamic = kinds.includes("dynamic");
  const isRequire = kinds.includes("require");
  const isReexport = kinds.includes("reexport");
  const isImport = kinds.includes("import");
  const isMultiKind = kinds.length > 1;

  let strokeClass = "stroke-emerald-600 dark:stroke-emerald-400";
  let strokeDasharray: string | undefined = undefined;

  if (isMultiKind) {
    strokeClass = "stroke-sky-600 dark:stroke-sky-400";
  } else if (isDynamic) {
    strokeClass = "stroke-amber-500 dark:stroke-amber-400";
    strokeDasharray = "5,4";
  } else if (isRequire) {
    strokeClass = "stroke-rose-600 dark:stroke-rose-400";
    strokeDasharray = "2,3";
  } else if (isReexport) {
    strokeClass = "stroke-violet-600 dark:stroke-violet-400";
  } else if (isImport) {
    strokeClass = "stroke-emerald-600 dark:stroke-emerald-400";
  }

  // Type-only edges are drawn thinner; regular edges are thicker
  const strokeWidth = typeOnlyOnly ? 1 : isMultiKind ? 2.5 : 1.75;

  // Blast dimming
  const isBlastActive = Boolean(blast);
  let isDimmed = false;
  if (isBlastActive && blast) {
    const affectedFiles = new Set(blast.impacts.map((i) => i.file));
    affectedFiles.add(blast.file);

    const sourceAffected =
      affectedFiles.has(source) ||
      blast.impacts.some((i) => i.file.startsWith(`${source}/`));
    const targetAffected =
      affectedFiles.has(target) ||
      blast.impacts.some((i) => i.file.startsWith(`${target}/`));

    if (!sourceAffected && !targetAffected) {
      isDimmed = true;
    }
  }

  const tooltipText =
    count > 1
      ? `${count} imports across folders (${kinds.join(", ")})${typeOnlyOnly ? " [type-only]" : ""}`
      : `${kinds.join(", ")}${typeOnlyOnly ? " (type-only)" : ""}`;

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        className={`transition-opacity duration-150 ${strokeClass} ${
          isDimmed ? "opacity-15" : "opacity-90"
        }`}
        style={{
          strokeWidth,
          strokeDasharray,
        }}
      />

      {count > 1 && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: "absolute",
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              pointerEvents: "all",
            }}
            title={tooltipText}
            className={`px-1.5 py-0.5 rounded-full text-[9px] font-mono font-bold shadow border cursor-help select-none ${
              isDimmed ? "opacity-30" : "opacity-100"
            } bg-white dark:bg-neutral-900 border-neutral-300 dark:border-neutral-700 text-neutral-700 dark:text-neutral-300 hover:scale-110 transition-transform`}
          >
            {count}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
});
