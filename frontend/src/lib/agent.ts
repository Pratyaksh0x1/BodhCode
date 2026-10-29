import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import { VITE_API_URL } from "./env";
import type { ReviewMode } from "./auth";

export type { ReviewMode };

export interface Proposal {
  id: number;
  user_id: number;
  repo_id: number;
  session_id: string | null;
  kind: "create" | "edit" | "delete";
  path: string;
  old_content: string | null;
  new_content: string | null;
  base_hash: string | null;
  rationale: string;
  blast_radius_count: number | null;
  status: "pending" | "accepted" | "rejected" | "applied" | "undone" | "stale";
  is_stale?: boolean;
  created_at: string;
  decided_at: string | null;
}

export interface ToolStep {
  step: number;
  tool: string;
  args: Record<string, unknown>;
  duration_ms: number;
  ok: boolean;
  summary: string;
}

export interface AgentVerification {
  verified_files: string[];
  flagged: string[];
}

export interface SelectionPayload {
  path: string;
  start_line: number;
  end_line: number;
  text: string;
}

export interface AgentHistoryItem {
  role: "user" | "assistant";
  content: string;
}

export interface AgentTurnRequest {
  message: string;
  history?: AgentHistoryItem[];
  review_mode?: ReviewMode;
  active_file?: string | null;
  selection?: SelectionPayload | null;
}

export interface AgentTurnCallbacks {
  onStep?: (step: ToolStep) => void;
  onProposal?: (proposal: Proposal) => void;
  onToken?: (token: string) => void;
  onVerification?: (verif: AgentVerification) => void;
  onDone?: (reason: string, steps: number) => void;
  onError?: (code: string, message: string) => void;
}

export async function streamAgentTurn(
  repoId: number | string,
  request: AgentTurnRequest,
  signal: AbortSignal,
  callbacks: AgentTurnCallbacks
): Promise<void> {
  const url = `${VITE_API_URL}/repos/${repoId}/agent`;
  let response: Response;

  try {
    response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "bodhcode",
      },
      credentials: "include",
      body: JSON.stringify(request),
      signal,
    });
  } catch (err: unknown) {
    if (err instanceof Error && err.name === "AbortError") {
      callbacks.onDone?.("cancelled", 0);
      return;
    }
    callbacks.onError?.(
      "network_error",
      err instanceof Error ? err.message : "Failed to connect to agent service"
    );
    return;
  }

  if (!response.ok) {
    let code = `http_${response.status}`;
    let message = response.statusText || "Agent request failed";
    try {
      const errorJson = (await response.json()) as {
        code?: string;
        detail?: string | { code?: string; message?: string };
      };
      if (typeof errorJson.detail === "string") {
        message = errorJson.detail;
      } else if (errorJson.detail && typeof errorJson.detail === "object") {
        if (errorJson.detail.code) code = errorJson.detail.code;
        if (errorJson.detail.message) message = errorJson.detail.message;
      }
      if (errorJson.code) code = errorJson.code;
    } catch {
      // Use fallback
    }
    callbacks.onError?.(code, message);
    return;
  }

  if (!response.body) {
    callbacks.onError?.("no_body", "No response body received from server");
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // Split SSE events separated by double newlines
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() || "";

      for (const block of blocks) {
        if (!block.trim()) continue;

        let eventType = "message";
        const dataLines: string[] = [];

        for (const line of block.split("\n")) {
          if (line.startsWith("event: ")) {
            eventType = line.substring(7).trim();
          } else if (line.startsWith("data: ")) {
            dataLines.push(line.substring(6));
          } else if (line.startsWith("data:")) {
            dataLines.push(line.substring(5));
          }
        }

        const rawData = dataLines.join("\n");
        if (!rawData) continue;

        try {
          const parsed = JSON.parse(rawData);

          if (eventType === "step") {
            callbacks.onStep?.(parsed as ToolStep);
          } else if (eventType === "proposal") {
            callbacks.onProposal?.(parsed as Proposal);
          } else if (eventType === "token") {
            callbacks.onToken?.(parsed.text || "");
          } else if (eventType === "verification") {
            callbacks.onVerification?.(parsed as AgentVerification);
          } else if (eventType === "done") {
            callbacks.onDone?.(parsed.reason || "complete", parsed.steps ?? 0);
          } else if (eventType === "error") {
            callbacks.onError?.(parsed.code || "unknown_error", parsed.message || "An error occurred");
          }
        } catch {
          // Failed to parse event JSON
        }
      }
    }
  } catch (err: unknown) {
    if (err instanceof Error && err.name === "AbortError") {
      callbacks.onDone?.("cancelled", 0);
      return;
    }
    callbacks.onError?.(
      "stream_error",
      err instanceof Error ? err.message : "Error reading event stream"
    );
  }
}

export const PROPOSALS_QUERY_KEY = (repoId: number | string) => ["proposals", repoId] as const;

export function useProposals(repoId: number | string, status?: string) {
  return useQuery<Proposal[], Error>({
    queryKey: [...PROPOSALS_QUERY_KEY(repoId), status || "all"],
    queryFn: () => {
      const url = status
        ? `/repos/${repoId}/proposals?status=${encodeURIComponent(status)}`
        : `/repos/${repoId}/proposals`;
      return api<Proposal[]>(url);
    },
    enabled: Boolean(repoId),
  });
}

export function useAcceptProposal(repoId: number | string) {
  const queryClient = useQueryClient();
  return useMutation<
    { status: string; proposal_id: number; path: string },
    Error,
    number
  >({
    mutationFn: (proposalId: number) =>
      api<{ status: string; proposal_id: number; path: string }>(
        `/proposals/${proposalId}/accept`,
        { method: "POST" }
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["proposals", repoId] });
      queryClient.invalidateQueries({ queryKey: ["files", repoId] });
    },
  });
}

export function useRejectProposal(repoId: number | string) {
  const queryClient = useQueryClient();
  return useMutation<{ status: string; proposal_id: number }, Error, number>({
    mutationFn: (proposalId: number) =>
      api<{ status: string; proposal_id: number }>(`/proposals/${proposalId}/reject`, {
        method: "POST",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["proposals", repoId] });
    },
  });
}

export function useEditProposal(repoId: number | string) {
  const queryClient = useQueryClient();
  return useMutation<
    { status: string; proposal_id: number; new_content: string },
    Error,
    { proposalId: number; newContent: string }
  >({
    mutationFn: ({ proposalId, newContent }) =>
      api<{ status: string; proposal_id: number; new_content: string }>(
        `/proposals/${proposalId}`,
        {
          method: "PUT",
          body: JSON.stringify({ new_content: newContent }),
        }
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["proposals", repoId] });
    },
  });
}

export interface BatchProposalResult {
  accepted?: Array<{ proposal_id: number; path: string; status: string }>;
  rejected?: Array<{ proposal_id: number; path: string; status: string }>;
  skipped_stale: Array<{ proposal_id: number; path: string }>;
  errors?: Array<{ proposal_id: number; error: string }>;
}

export function useAcceptAllProposals(repoId: number | string) {
  const queryClient = useQueryClient();
  return useMutation<BatchProposalResult, Error, void>({
    mutationFn: () =>
      api<BatchProposalResult>("/proposals/accept-all", {
        method: "POST",
        body: JSON.stringify({ repo_id: Number(repoId) }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["proposals", repoId] });
      queryClient.invalidateQueries({ queryKey: ["files", repoId] });
    },
  });
}

export function useRejectAllProposals(repoId: number | string) {
  const queryClient = useQueryClient();
  return useMutation<BatchProposalResult, Error, void>({
    mutationFn: () =>
      api<BatchProposalResult>("/proposals/reject-all", {
        method: "POST",
        body: JSON.stringify({ repo_id: Number(repoId) }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["proposals", repoId] });
    },
  });
}

export function useUndoProposal(repoId: number | string) {
  const queryClient = useQueryClient();
  return useMutation<
    { status: string; proposal_id: number; path: string; restored: boolean },
    Error,
    number
  >({
    mutationFn: (proposalId: number) =>
      api<{ status: string; proposal_id: number; path: string; restored: boolean }>(
        `/proposals/${proposalId}/undo`,
        { method: "POST" }
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["proposals", repoId] });
      queryClient.invalidateQueries({ queryKey: ["files", repoId] });
    },
  });
}
