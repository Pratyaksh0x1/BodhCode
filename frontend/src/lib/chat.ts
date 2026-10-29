import { VITE_API_URL } from "./env";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ToolStep {
  step: number;
  tool: string;
  args: Record<string, unknown>;
  duration_ms: number;
  ok: boolean;
  summary: string;
}

export interface ChatVerification {
  verified_files: string[];
  flagged: string[];
}

export interface StreamChatCallbacks {
  onStep?: (step: ToolStep) => void;
  onToken?: (text: string) => void;
  onVerification?: (verif: ChatVerification) => void;
  onDone?: (reason: string) => void;
  onError?: (code: string, message: string) => void;
}

export async function streamRepoChat(
  repoId: number | string,
  messages: ChatMessage[],
  language: string,
  signal: AbortSignal,
  callbacks: StreamChatCallbacks
): Promise<void> {
  const url = `${VITE_API_URL}/repos/${repoId}/chat`;
  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "bodhcode",
      },
      credentials: "include",
      body: JSON.stringify({
        messages,
        language,
      }),
      signal,
    });
  } catch (err: unknown) {
    if (err instanceof Error && err.name === "AbortError") {
      callbacks.onDone?.("cancelled");
      return;
    }
    callbacks.onError?.(
      "network_error",
      err instanceof Error ? err.message : "Failed to connect to chat service"
    );
    return;
  }

  if (!response.ok) {
    let code = `http_${response.status}`;
    let message = response.statusText || "Chat request failed";
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
      // Fallback to response statusText
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

      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";

      for (const part of parts) {
        const trimmed = part.trim();
        if (!trimmed || trimmed.startsWith(":")) {
          // Heartbeat comment or empty line
          continue;
        }

        const lines = trimmed.split("\n");
        for (const line of lines) {
          if (line.startsWith("data:")) {
            const dataStr = line.slice(5).trim();
            if (!dataStr) continue;
            try {
              const event = JSON.parse(dataStr);
              if (event.type === "step") {
                callbacks.onStep?.(event);
              } else if (event.type === "token") {
                callbacks.onToken?.(event.text || "");
              } else if (event.type === "verification") {
                callbacks.onVerification?.({
                  verified_files: event.verified_files || [],
                  flagged: event.flagged || [],
                });
              } else if (event.type === "done") {
                callbacks.onDone?.(event.finish_reason || "stop");
              } else if (event.type === "error") {
                callbacks.onError?.(
                  event.code || "unknown",
                  event.message || "An error occurred"
                );
              }
            } catch (parseErr) {
              console.error("Failed to parse SSE JSON chunk:", line, parseErr);
            }
          }
        }
      }
    }
  } catch (err: unknown) {
    if (err instanceof Error && err.name === "AbortError") {
      callbacks.onDone?.("cancelled");
      return;
    }
    callbacks.onError?.(
      "stream_error",
      err instanceof Error ? err.message : String(err)
    );
  } finally {
    reader.releaseLock();
  }
}
