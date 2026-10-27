import { useState } from "react";
import {
  useAcceptAllProposals,
  useRejectAllProposals,
  type BatchProposalResult,
} from "../../../lib/agent";

interface AcceptAllBarProps {
  repoId: number | string;
  pendingCount: number;
  onBatchDecided?: () => void;
}

export function AcceptAllBar({
  repoId,
  pendingCount,
  onBatchDecided,
}: AcceptAllBarProps) {
  const [lastResult, setLastResult] = useState<BatchProposalResult | null>(null);

  const acceptAllMutation = useAcceptAllProposals(repoId);
  const rejectAllMutation = useRejectAllProposals(repoId);

  if (pendingCount < 2 && !lastResult) {
    return null;
  }

  const handleAcceptAll = async () => {
    try {
      const res = await acceptAllMutation.mutateAsync();
      setLastResult(res);
      onBatchDecided?.();
    } catch {
      // Error handled
    }
  };

  const handleRejectAll = async () => {
    try {
      const res = await rejectAllMutation.mutateAsync();
      setLastResult(res);
      onBatchDecided?.();
    } catch {
      // Error handled
    }
  };

  return (
    <div className="p-2.5 rounded-lg border border-neutral-800 bg-neutral-900/90 shadow-md space-y-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 text-xs text-neutral-300">
          <span className="w-2 h-2 rounded-full bg-orange-400" />
          <span>
            <strong>{pendingCount}</strong> proposals pending review
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleRejectAll}
            disabled={rejectAllMutation.isPending || acceptAllMutation.isPending}
            className="px-2.5 py-1 rounded bg-neutral-800 hover:bg-neutral-700 text-neutral-300 text-xs font-medium transition-colors cursor-pointer disabled:opacity-50"
          >
            {rejectAllMutation.isPending ? "Rejecting..." : "Reject All"}
          </button>
          <button
            type="button"
            onClick={handleAcceptAll}
            disabled={acceptAllMutation.isPending || rejectAllMutation.isPending}
            className="px-3 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium transition-colors cursor-pointer shadow-sm disabled:opacity-50"
          >
            {acceptAllMutation.isPending ? "Applying..." : "Accept All"}
          </button>
        </div>
      </div>

      {lastResult && lastResult.skipped_stale.length > 0 && (
        <div className="text-[11px] text-amber-400 bg-amber-950/40 border border-amber-800/40 px-2 py-1 rounded">
          Skipped {lastResult.skipped_stale.length} stale proposal(s) whose files changed.
        </div>
      )}
    </div>
  );
}
