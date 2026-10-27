import { useState } from "react";
import { DiffEditor } from "@monaco-editor/react";
import type { Proposal } from "../../../lib/agent";
import {
  useAcceptProposal,
  useEditProposal,
  useRejectProposal,
  useUndoProposal,
} from "../../../lib/agent";
import type { ResolvedEditorTheme } from "../../../lib/theme";

interface ProposalCardProps {
  proposal: Proposal;
  repoId: number | string;
  theme: ResolvedEditorTheme;
  onProposalDecided?: () => void;
  onOpenFile?: (path: string) => void;
}

export function ProposalCard({
  proposal,
  repoId,
  theme,
  onProposalDecided,
  onOpenFile,
}: ProposalCardProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editedContent, setEditedContent] = useState(proposal.new_content || "");
  const [diffExpanded, setDiffExpanded] = useState(true);

  const acceptMutation = useAcceptProposal(repoId);
  const rejectMutation = useRejectProposal(repoId);
  const editMutation = useEditProposal(repoId);
  const undoMutation = useUndoProposal(repoId);

  const isPending = proposal.status === "pending" && !proposal.is_stale;
  const isApplied = proposal.status === "applied";
  const isStale = proposal.status === "stale" || Boolean(proposal.is_stale);
  const isRejected = proposal.status === "rejected";
  const isUndone = proposal.status === "undone";

  const handleAccept = async () => {
    try {
      await acceptMutation.mutateAsync(proposal.id);
      onProposalDecided?.();
    } catch {
      // Error handled by query/mutation state
    }
  };

  const handleReject = async () => {
    try {
      await rejectMutation.mutateAsync(proposal.id);
      onProposalDecided?.();
    } catch {
      // Error handled
    }
  };

  const handleSaveEdit = async () => {
    try {
      await editMutation.mutateAsync({
        proposalId: proposal.id,
        newContent: editedContent,
      });
      setIsEditing(false);
      onProposalDecided?.();
    } catch {
      // Error handled
    }
  };

  const handleUndo = async () => {
    try {
      await undoMutation.mutateAsync(proposal.id);
      onProposalDecided?.();
    } catch {
      // Error handled
    }
  };

  const kindBadgeColor =
    proposal.kind === "create"
      ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
      : proposal.kind === "delete"
      ? "bg-rose-500/10 text-rose-400 border-rose-500/20"
      : "bg-amber-500/10 text-amber-400 border-amber-500/20";

  return (
    <div
      className={`border rounded-lg bg-neutral-900/60 overflow-hidden text-xs shadow-sm ${
        isStale
          ? "border-rose-900/40 opacity-80"
          : isApplied
          ? "border-emerald-900/40"
          : "border-neutral-800"
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 bg-neutral-900 border-b border-neutral-800 gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span
            className={`px-1.5 py-0.5 rounded text-[10px] font-mono uppercase font-bold border ${kindBadgeColor}`}
          >
            {proposal.kind}
          </span>
          <button
            type="button"
            onClick={() => onOpenFile?.(proposal.path)}
            title="Open in editor"
            className="font-mono text-neutral-200 hover:text-orange-400 transition-colors truncate text-left cursor-pointer"
          >
            {proposal.path}
          </button>
        </div>

        {/* Status indicator */}
        <div className="flex items-center gap-1.5 shrink-0">
          {isApplied && (
            <span className="px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 text-[10px] font-medium">
              Applied
            </span>
          )}
          {isUndone && (
            <span className="px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-300 text-[10px] font-medium">
              Undone
            </span>
          )}
          {isRejected && (
            <span className="px-1.5 py-0.5 rounded bg-neutral-800 text-neutral-400 text-[10px] font-medium">
              Rejected
            </span>
          )}
          {isStale && (
            <span className="px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-300 text-[10px] font-medium">
              Stale
            </span>
          )}
          {isPending && (
            <span className="px-1.5 py-0.5 rounded bg-orange-500/20 text-orange-300 text-[10px] font-medium">
              Pending
            </span>
          )}

          <button
            type="button"
            onClick={() => setDiffExpanded(!diffExpanded)}
            title={diffExpanded ? "Collapse diff" : "Expand diff"}
            className="p-1 rounded text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800 cursor-pointer text-[10px]"
          >
            {diffExpanded ? "▲" : "▼"}
          </button>
        </div>
      </div>

      {/* Rationale & Blast Radius */}
      <div className="px-3 py-2 space-y-1.5 border-b border-neutral-800/60 bg-neutral-950/40">
        <p className="text-neutral-300">{proposal.rationale}</p>

        {proposal.blast_radius_count !== null && proposal.blast_radius_count !== undefined && (
          <div className="flex items-center gap-1.5 text-[11px] text-neutral-400">
            <span className="text-amber-400 font-semibold">⚡ Blast radius:</span>
            <span>
              Changing this affects{" "}
              <strong className="text-neutral-200">{proposal.blast_radius_count}</strong> files
            </span>
            <span
              title="Based on the original commit's graph"
              className="cursor-help text-neutral-500 hover:text-neutral-400"
            >
              ⓘ
            </span>
          </div>
        )}

        {isStale && (
          <div className="mt-1 px-2.5 py-1.5 rounded bg-rose-950/50 border border-rose-800/50 text-rose-300 text-[11px] flex items-center gap-1.5">
            <span>⚠️</span>
            <span>File changed — ask the agent to redo</span>
          </div>
        )}
      </div>

      {/* Diff / Edit Area */}
      {diffExpanded && (
        <div className="border-b border-neutral-800 bg-neutral-950">
          {isEditing ? (
            <div className="p-2 space-y-2">
              <div className="flex items-center justify-between text-[11px] text-neutral-400">
                <span>Edit proposed content:</span>
                <span className="font-mono text-[10px] text-neutral-500">{proposal.path}</span>
              </div>
              <textarea
                value={editedContent}
                onChange={(e) => setEditedContent(e.target.value)}
                rows={10}
                className="w-full font-mono text-xs p-2 rounded bg-neutral-900 border border-neutral-700 text-neutral-200 focus:outline-none focus:border-orange-500 resize-y"
              />
              <div className="flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setEditedContent(proposal.new_content || "");
                    setIsEditing(false);
                  }}
                  className="px-2.5 py-1 rounded bg-neutral-800 hover:bg-neutral-700 text-neutral-300 transition-colors cursor-pointer text-xs"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleSaveEdit}
                  disabled={editMutation.isPending}
                  className="px-2.5 py-1 rounded bg-orange-600 hover:bg-orange-500 text-white font-medium transition-colors cursor-pointer text-xs disabled:opacity-50"
                >
                  {editMutation.isPending ? "Saving..." : "Save Edit"}
                </button>
              </div>
            </div>
          ) : (
            <div className="h-44 w-full">
              <DiffEditor
                original={proposal.old_content ?? ""}
                modified={proposal.new_content ?? ""}
                theme={theme}
                options={{
                  readOnly: true,
                  renderSideBySide: false,
                  automaticLayout: true,
                  minimap: { enabled: false },
                  fontSize: 11,
                  lineNumbers: "on",
                  scrollBeyondLastLine: false,
                }}
              />
            </div>
          )}
        </div>
      )}

      {/* Actions Toolbar */}
      <div className="flex items-center justify-between px-3 py-2 bg-neutral-900/90 text-xs">
        <div className="text-[11px] text-neutral-500">
          #{proposal.id} • {new Date(proposal.created_at).toLocaleTimeString()}
        </div>

        <div className="flex items-center gap-2">
          {isPending && !isEditing && (
            <>
              <button
                type="button"
                onClick={() => setIsEditing(true)}
                className="px-2.5 py-1 rounded bg-neutral-800 hover:bg-neutral-700 text-neutral-300 transition-colors cursor-pointer"
              >
                Edit
              </button>
              <button
                type="button"
                onClick={handleReject}
                disabled={rejectMutation.isPending}
                className="px-2.5 py-1 rounded bg-neutral-800 hover:bg-rose-950 hover:text-rose-300 text-neutral-400 transition-colors cursor-pointer disabled:opacity-50"
              >
                {rejectMutation.isPending ? "Rejecting..." : "Reject"}
              </button>
              <button
                type="button"
                onClick={handleAccept}
                disabled={acceptMutation.isPending}
                className="px-3 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-medium transition-colors cursor-pointer shadow-sm disabled:opacity-50"
              >
                {acceptMutation.isPending ? "Applying..." : "Accept"}
              </button>
            </>
          )}

          {isApplied && (
            <button
              type="button"
              onClick={handleUndo}
              disabled={undoMutation.isPending}
              className="px-2.5 py-1 rounded bg-neutral-800 hover:bg-purple-900 hover:text-purple-200 text-purple-300 transition-colors cursor-pointer disabled:opacity-50 flex items-center gap-1.5"
            >
              <span>↩</span>
              <span>{undoMutation.isPending ? "Undoing..." : "Undo"}</span>
            </button>
          )}

          {acceptMutation.isError && (
            <span className="text-[11px] text-rose-400 font-medium">
              {acceptMutation.error?.message || "Failed to accept"}
            </span>
          )}
          {undoMutation.isError && (
            <span className="text-[11px] text-rose-400 font-medium">
              {undoMutation.error?.message || "Failed to undo"}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
