import { useState } from "react";
import type { ToolStep } from "../../../lib/agent";

interface ToolStepRowProps {
  step: ToolStep;
}

export function ToolStepRow({ step }: ToolStepRowProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border border-neutral-800 rounded bg-neutral-900/40 text-xs overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-2.5 py-1.5 hover:bg-neutral-800/50 text-left transition-colors cursor-pointer select-none"
      >
        <div className="flex items-center gap-2 min-w-0">
          <span
            className={`w-2 h-2 rounded-full shrink-0 ${
              step.ok ? "bg-emerald-500" : "bg-rose-500"
            }`}
          />
          <span className="font-mono font-medium text-orange-400 shrink-0">
            {step.tool}
          </span>
          <span className="text-neutral-300 truncate">
            {step.summary || JSON.stringify(step.args)}
          </span>
        </div>

        <div className="flex items-center gap-2 shrink-0 text-[10px] text-neutral-500">
          {step.duration_ms > 0 && <span>{Math.round(step.duration_ms)}ms</span>}
          <span className="text-neutral-400 font-mono">
            {expanded ? "▲" : "▼"}
          </span>
        </div>
      </button>

      {expanded && (
        <div className="px-2.5 py-2 border-t border-neutral-800 bg-neutral-950/80 font-mono text-[11px] text-neutral-400 overflow-x-auto">
          <pre>{JSON.stringify(step.args, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}
