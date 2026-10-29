import { useEffect, useRef, useState } from "react";
import {
  streamAgentTurn,
  useProposals,
  type AgentHistoryItem,
  type AgentVerification,
  type Proposal,
  type ReviewMode,
  type SelectionPayload,
  type ToolStep,
} from "../../../lib/agent";
import { useMe } from "../../../lib/auth";
import type { ResolvedEditorTheme } from "../../../lib/theme";
import { AcceptAllBar } from "./AcceptAllBar";
import { ProposalCard } from "./ProposalCard";
import { ToolStepRow } from "./ToolStepRow";

export interface PendingSelection {
  path: string;
  start_line: number;
  end_line: number;
  text: string;
  action: "ask" | "edit";
}

interface AgentPanelProps {
  repoId: number | string;
  activeFilePath: string | null;
  pendingSelection?: PendingSelection | null;
  onClearSelection?: () => void;
  onOpenFile?: (path: string) => void;
  onClose?: () => void;
  theme: ResolvedEditorTheme;
  onFileModified?: () => void;
}

interface AgentTurnState {
  id: string;
  role: "user" | "assistant";
  content: string;
  steps: ToolStep[];
  proposals: Proposal[];
  verification: AgentVerification | null;
  isStreaming: boolean;
  error: string | null;
}

export function AgentPanel({
  repoId,
  activeFilePath,
  pendingSelection,
  onClearSelection,
  onOpenFile,
  onClose,
  theme,
  onFileModified,
}: AgentPanelProps) {
  const { data: user } = useMe();
  const defaultMode: ReviewMode = (user?.review_mode as ReviewMode) || "review";
  const [reviewMode, setReviewMode] = useState<ReviewMode>(defaultMode);
  const [agentEngine, setAgentEngine] = useState<"copilot" | "chatgpt" | "grok">("copilot");

  // Sync default mode once user loads
  useEffect(() => {
    if (user?.review_mode) {
      setReviewMode(user.review_mode as ReviewMode);
    }
  }, [user?.review_mode]);

  const [inputMessage, setInputMessage] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [turns, setTurns] = useState<AgentTurnState[]>([]);
  const abortControllerRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Proposals query for this repository
  const { data: proposals, refetch: refetchProposals } = useProposals(repoId);
  const pendingProposals = proposals?.filter((p) => p.status === "pending" && !p.is_stale) || [];

  // Prepopulate input if pendingSelection changes
  useEffect(() => {
    if (pendingSelection) {
      if (pendingSelection.action === "edit") {
        setInputMessage(
          `Please edit the selected lines in \`${pendingSelection.path}\`: `
        );
      } else {
        setInputMessage(
          `Explain this code snippet in \`${pendingSelection.path}\`: `
        );
      }
    }
  }, [pendingSelection]);

  // Auto scroll to bottom of messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [turns, isStreaming]);

  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsStreaming(false);
  };

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const trimmed = inputMessage.trim();
    if (!trimmed || isStreaming) return;

    const userTurn: AgentTurnState = {
      id: `user-${Date.now()}`,
      role: "user",
      content: trimmed,
      steps: [],
      proposals: [],
      verification: null,
      isStreaming: false,
      error: null,
    };

    const assistantTurnId = `asst-${Date.now()}`;
    const assistantTurn: AgentTurnState = {
      id: assistantTurnId,
      role: "assistant",
      content: "",
      steps: [],
      proposals: [],
      verification: null,
      isStreaming: true,
      error: null,
    };

    setTurns((prev) => [...prev, userTurn, assistantTurn]);
    setInputMessage("");
    setIsStreaming(true);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    // Convert existing turns into history items
    const history: AgentHistoryItem[] = turns.map((t) => ({
      role: t.role,
      content: t.content,
    }));

    const selectionPayload: SelectionPayload | null = pendingSelection
      ? {
          path: pendingSelection.path,
          start_line: pendingSelection.start_line,
          end_line: pendingSelection.end_line,
          text: pendingSelection.text,
        }
      : null;

    if (pendingSelection) {
      onClearSelection?.();
    }

    try {
      await streamAgentTurn(
        repoId,
        {
          message: trimmed,
          history,
          review_mode: reviewMode,
          active_file: activeFilePath,
          selection: selectionPayload,
        },
        controller.signal,
        {
          onStep: (step) => {
            setTurns((prev) =>
              prev.map((t) =>
                t.id === assistantTurnId
                  ? { ...t, steps: [...t.steps, step] }
                  : t
              )
            );
          },
          onProposal: (proposal) => {
            setTurns((prev) =>
              prev.map((t) =>
                t.id === assistantTurnId
                  ? { ...t, proposals: [...t.proposals, proposal] }
                  : t
              )
            );
            refetchProposals();
            onFileModified?.();
          },
          onToken: (token) => {
            setTurns((prev) =>
              prev.map((t) =>
                t.id === assistantTurnId
                  ? { ...t, content: t.content + token }
                  : t
              )
            );
          },
          onVerification: (verif) => {
            setTurns((prev) =>
              prev.map((t) =>
                t.id === assistantTurnId ? { ...t, verification: verif } : t
              )
            );
          },
          onDone: () => {
            setTurns((prev) =>
              prev.map((t) =>
                t.id === assistantTurnId ? { ...t, isStreaming: false } : t
              )
            );
            setIsStreaming(false);
            abortControllerRef.current = null;
            refetchProposals();
          },
          onError: (_, message) => {
            setTurns((prev) =>
              prev.map((t) =>
                t.id === assistantTurnId
                  ? { ...t, error: message, isStreaming: false }
                  : t
              )
            );
            setIsStreaming(false);
            abortControllerRef.current = null;
          },
        }
      );
    } catch (err: unknown) {
      setTurns((prev) =>
        prev.map((t) =>
          t.id === assistantTurnId
            ? {
                ...t,
                error: err instanceof Error ? err.message : "Turn failed",
                isStreaming: false,
              }
            : t
        )
      );
      setIsStreaming(false);
      abortControllerRef.current = null;
    }
  };

  const renderContentWithMentions = (
    text: string,
    verification: AgentVerification | null
  ) => {
    if (!verification) {
      return <p className="whitespace-pre-wrap">{text}</p>;
    }

    const { verified_files, flagged } = verification;
    const tokens = text.split(/(`[^`]+`|\s+)/);

    return (
      <div className="whitespace-pre-wrap leading-relaxed">
        {tokens.map((token, idx) => {
          const matchBacktick = token.match(/^`([^`]+)`$/);
          const candidate = matchBacktick ? matchBacktick[1] : token;

          if (verified_files.includes(candidate)) {
            return (
              <button
                key={idx}
                type="button"
                onClick={() => onOpenFile?.(candidate)}
                title="Click to open verified file"
                className="inline-flex items-center font-mono text-[11px] px-1 py-0.2 mx-0.5 rounded bg-emerald-950/60 text-emerald-300 border border-emerald-800/60 hover:bg-emerald-900/80 cursor-pointer font-medium"
              >
                <span>📄 {candidate}</span>
              </button>
            );
          }

          if (flagged.includes(candidate)) {
            return (
              <span
                key={idx}
                title="Warning: File does not exist in graph or repository"
                className="inline-flex items-center font-mono text-[11px] px-1 py-0.2 mx-0.5 rounded bg-amber-950/60 text-amber-300 border border-amber-800/60 cursor-help"
              >
                <span>⚠️ {candidate}</span>
              </span>
            );
          }

          return <span key={idx}>{token}</span>;
        })}
      </div>
    );
  };

  return (
    <div className="h-full flex flex-col bg-neutral-950 border-l border-neutral-800 text-neutral-200 overflow-hidden select-none">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 bg-neutral-900 border-b border-neutral-800 text-xs shrink-0 font-semibold">
        <div className="flex items-center gap-1.5 text-neutral-200">
          <span className="text-orange-400">⚡</span>
          <span>BodhCode Agent</span>
        </div>

        <div className="flex items-center gap-2">
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="p-1 rounded text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800 cursor-pointer"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Review Mode Selector */}
      <div className="px-3 py-2 bg-neutral-900/60 border-b border-neutral-800 text-xs space-y-1 shrink-0">
        <div className="flex items-center justify-between gap-2 pb-1 mb-1 border-b border-neutral-800/60">
          <span className="text-neutral-400 text-[11px] font-medium">AI Engine:</span>
          <select
            value={agentEngine}
            onChange={(e) => setAgentEngine(e.target.value as "copilot" | "chatgpt" | "grok")}
            className="px-2 py-0.5 rounded bg-neutral-800 border border-neutral-700 text-neutral-200 text-xs focus:outline-none focus:border-orange-500 cursor-pointer"
          >
            <option value="copilot">🐙 GitHub Copilot</option>
            <option value="chatgpt">⚡ ChatGPT / Codex</option>
            <option value="grok">🧠 Grok 120B</option>
          </select>
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-neutral-400 text-[11px] font-medium">Review Mode:</span>
          <select
            value={reviewMode}
            onChange={(e) => setReviewMode(e.target.value as ReviewMode)}
            className="px-2 py-1 rounded bg-neutral-800 border border-neutral-700 text-neutral-200 text-xs focus:outline-none focus:border-orange-500 cursor-pointer"
          >
            <option value="review">Review every change</option>
            <option value="auto">Auto-accept edits this session</option>
            <option value="readonly">Read-only plan</option>
          </select>
        </div>

        <p className="text-[11px] text-neutral-500">
          {reviewMode === "review" &&
            "Changes become proposal diffs. Inspect and accept before files change."}
          {reviewMode === "auto" &&
            "Edits and creates apply immediately with Undo available. Deletions still queue."}
          {reviewMode === "readonly" &&
            "Write tools are blocked. The agent explains architecture and plans in text."}
        </p>
      </div>

      {/* Accept-All / Reject-All Bar */}
      {pendingProposals.length >= 2 && (
        <div className="p-2 border-b border-neutral-800 bg-neutral-900/40 shrink-0">
          <AcceptAllBar
            repoId={repoId}
            pendingCount={pendingProposals.length}
            onBatchDecided={() => {
              refetchProposals();
              onFileModified?.();
            }}
          />
        </div>
      )}

      {/* Messages List Area */}
      <div className="flex-1 overflow-y-auto p-3 space-y-4">
        {turns.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center text-center p-4 text-neutral-500 gap-2">
            <span className="text-2xl text-orange-400">🤖</span>
            <p className="text-xs max-w-xs font-medium text-neutral-400">
              Ask BodhCode Agent to inspect code, find dependencies, or safely edit files.
            </p>
            <div className="text-[11px] text-neutral-500 space-y-1">
              <p>• "Add a null check to config loader in src/app.ts"</p>
              <p>• "Which files import src/types.ts?"</p>
              <p>• "Search for calculateDiscount usages"</p>
            </div>
          </div>
        )}

        {turns.map((turn) => (
          <div key={turn.id} className="space-y-2">
            {turn.role === "user" ? (
              <div className="flex justify-end">
                <div className="max-w-[85%] rounded-lg px-3 py-2 bg-orange-600/20 border border-orange-500/30 text-neutral-100 text-xs">
                  {turn.content}
                </div>
              </div>
            ) : (
              <div className="space-y-2.5 max-w-[95%]">
                {/* Step rows */}
                {turn.steps.length > 0 && (
                  <div className="space-y-1.5">
                    {turn.steps.map((step, idx) => (
                      <ToolStepRow key={idx} step={step} />
                    ))}
                  </div>
                )}

                {/* Assistant Answer Content */}
                {turn.content && (
                  <div className="text-xs text-neutral-200 bg-neutral-900/40 p-2.5 rounded-lg border border-neutral-800/60">
                    {renderContentWithMentions(turn.content, turn.verification)}
                  </div>
                )}

                {/* Proposal Cards emitted in this turn */}
                {turn.proposals.map((prop) => (
                  <ProposalCard
                    key={prop.id}
                    proposal={prop}
                    repoId={repoId}
                    theme={theme}
                    onOpenFile={onOpenFile}
                    onProposalDecided={() => {
                      refetchProposals();
                      onFileModified?.();
                    }}
                  />
                ))}

                {/* Error Banner */}
                {turn.error && (
                  <div className="p-2 rounded bg-rose-950/60 border border-rose-800/60 text-rose-300 text-xs">
                    {turn.error}
                  </div>
                )}

                {/* Streaming indicator */}
                {turn.isStreaming && (
                  <div className="flex items-center gap-1.5 text-[11px] text-orange-400 font-mono">
                    <span className="w-1.5 h-1.5 rounded-full bg-orange-400 animate-ping" />
                    <span>Agent thinking...</span>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="p-2.5 border-t border-neutral-800 bg-neutral-900/80 space-y-2 shrink-0">
        {/* Selection Chip */}
        {pendingSelection && (
          <div className="flex items-center justify-between px-2 py-1 rounded bg-orange-950/40 border border-orange-800/40 text-[11px] text-orange-300">
            <span className="truncate">
              📍 Selection: <span className="font-mono">{pendingSelection.path}:{pendingSelection.start_line}-{pendingSelection.end_line}</span>
            </span>
            <button
              type="button"
              onClick={onClearSelection}
              className="text-neutral-400 hover:text-neutral-200 cursor-pointer ml-1"
            >
              ✕
            </button>
          </div>
        )}

        <form onSubmit={handleSubmit} className="flex gap-1.5 items-end">
          <textarea
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSubmit();
              }
            }}
            rows={2}
            placeholder={
              reviewMode === "readonly"
                ? "Ask agent a question or describe an architectural plan..."
                : "Ask agent to inspect, refactor, or edit code (Enter to send)..."
            }
            className="flex-1 text-xs p-2 rounded-lg bg-neutral-950 border border-neutral-700 text-neutral-200 focus:outline-none focus:border-orange-500 resize-none font-sans"
          />

          {isStreaming ? (
            <button
              type="button"
              onClick={handleStop}
              className="px-3 py-2 rounded-lg bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold transition-colors cursor-pointer shrink-0"
            >
              Stop
            </button>
          ) : (
            <button
              type="submit"
              disabled={!inputMessage.trim()}
              className="px-3 py-2 rounded-lg bg-orange-600 hover:bg-orange-500 text-white text-xs font-semibold transition-colors cursor-pointer shrink-0 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Send
            </button>
          )}
        </form>
      </div>
    </div>
  );
}
