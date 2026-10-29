import { memo, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { useReactFlow } from "@xyflow/react";
import { useGraphStore } from "../../store/graphStore";
import { useMe } from "../../lib/auth";
import {
  streamRepoChat,
  type ChatMessage,
  type ChatVerification,
  type ToolStep,
} from "../../lib/chat";

interface ChatDrawerProps {
  repoId: number | string;
  repoStatus?: string;
}

interface ChatUiMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  steps?: ToolStep[];
  verification?: ChatVerification;
  streaming?: boolean;
  error?: string;
}

export const ChatDrawer = memo(function ChatDrawer({
  repoId,
  repoStatus = "ready",
}: ChatDrawerProps) {
  const isChatOpen = useGraphStore((s) => s.isChatOpen);
  const setChatOpen = useGraphStore((s) => s.setChatOpen);
  const selectedFileId = useGraphStore((s) => s.selectedFileId);
  const expandPathTo = useGraphStore((s) => s.expandPathTo);
  const select = useGraphStore((s) => s.select);
  const { fitView } = useReactFlow();

  const { data: user } = useMe();
  const currentLanguageCode = user?.preferred_language || "en";

  const [messages, setMessages] = useState<ChatUiMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll to bottom of messages container
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView?.({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Clean up in-flight requests on unmount
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  const handleNavigate = (targetId: string) => {
    expandPathTo(targetId);
    select(targetId);
    setTimeout(() => {
      fitView({
        nodes: [{ id: targetId }],
        duration: 400,
        maxZoom: 1.25,
      });
    }, 60);
  };

  const handleSend = async (textToSend?: string) => {
    const messageText = (textToSend ?? input).trim();
    if (!messageText || isStreaming || repoStatus !== "ready") {
      return;
    }

    const userMsgId = `u-${Date.now()}`;
    const assistantMsgId = `a-${Date.now() + 1}`;

    const userMessage: ChatUiMessage = {
      id: userMsgId,
      role: "user",
      content: messageText,
    };

    const assistantMessage: ChatUiMessage = {
      id: assistantMsgId,
      role: "assistant",
      content: "",
      steps: [],
      streaming: true,
    };

    const historyForApi: ChatMessage[] = [
      ...messages
        .filter((m) => !m.error)
        .map((m) => ({
          role: m.role,
          content: m.content,
        })),
      { role: "user", content: messageText },
    ];

    setMessages((prev) => [...prev, userMessage, assistantMessage]);
    setInput("");
    setIsStreaming(true);

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    await streamRepoChat(
      repoId,
      historyForApi,
      currentLanguageCode,
      abortController.signal,
      {
        onStep: (step) => {
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMsgId
                ? { ...msg, steps: [...(msg.steps || []), step] }
                : msg
            )
          );
        },
        onToken: (text) => {
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMsgId
                ? { ...msg, content: msg.content + text }
                : msg
            )
          );
        },
        onVerification: (verif) => {
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMsgId
                ? { ...msg, verification: verif }
                : msg
            )
          );
        },
        onDone: () => {
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMsgId
                ? { ...msg, streaming: false }
                : msg
            )
          );
          setIsStreaming(false);
          abortControllerRef.current = null;
        },
        onError: (code, errorMsg) => {
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMsgId
                ? {
                    ...msg,
                    streaming: false,
                    error:
                      code === "concurrent_limit"
                        ? "Another chat request is currently in progress for this repository. Please wait."
                        : errorMsg,
                  }
                : msg
            )
          );
          setIsStreaming(false);
          abortControllerRef.current = null;
        },
      }
    );
  };

  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsStreaming(false);
    }
  };

  const handleClear = () => {
    handleStop();
    setMessages([]);
  };

  const starterTargetFile = useMemo(() => {
    return selectedFileId || "src/index.ts";
  }, [selectedFileId]);

  const starterQuestions = useMemo(
    () => [
      "What are the most depended-on files in this repository?",
      "Are there any circular dependencies?",
      `What breaks if I change ${starterTargetFile}?`,
    ],
    [starterTargetFile]
  );

  const formatToolTitle = (step: ToolStep) => {
    const file = (step.args?.file as string) || (step.args?.pattern as string) || "";
    switch (step.tool) {
      case "list_dependencies":
        return `Checked imports of ${file || "file"}`;
      case "list_dependents":
        return `Checked imported-by for ${file || "file"}`;
      case "blast_radius":
        return `Computed blast radius for ${file || "file"}`;
      case "find_files":
        return `Found files matching "${file}"`;
      case "get_file_exports":
        return `Inspected exports of ${file || "file"}`;
      case "read_file":
        return `Read source snippet of ${file || "file"}`;
      case "get_graph_summary":
        return "Loaded repository topology summary";
      default:
        return `Executed ${step.tool}`;
    }
  };

  if (!isChatOpen) {
    return null;
  }

  const isRepoReady = repoStatus === "ready";

  return (
    <aside
      id="repo-chat-drawer"
      aria-label="Repository AI Chat"
      className="fixed top-16 right-0 bottom-0 w-96 md:w-[420px] bg-white/95 dark:bg-neutral-900/95 backdrop-blur-md border-l border-neutral-200 dark:border-neutral-800 shadow-2xl flex flex-col z-40 select-none text-neutral-800 dark:text-neutral-100 transition-transform duration-200"
    >
      {/* Header */}
      <div className="p-3.5 border-b border-neutral-200 dark:border-neutral-800 flex items-center justify-between gap-2 bg-neutral-50/50 dark:bg-neutral-900/50">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-lg bg-orange-500/10 dark:bg-orange-500/20 text-orange-600 dark:text-orange-400 flex items-center justify-center font-bold text-xs">
            💬
          </div>
          <div>
            <h3 className="text-sm font-bold leading-tight">Repository Chat</h3>
            <span className="text-[10px] text-neutral-500 dark:text-neutral-400 block">
              Grounded in dependency graph
            </span>
          </div>
        </div>

        <div className="flex items-center gap-1">
          {messages.length > 0 && (
            <button
              type="button"
              onClick={handleClear}
              className="text-[11px] px-2 py-1 rounded text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors cursor-pointer"
              title="Reset transient conversation"
            >
              Clear
            </button>
          )}

          <button
            type="button"
            aria-label="Close chat drawer"
            onClick={() => setChatOpen(false)}
            className="p-1 rounded-lg text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors cursor-pointer"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      {/* Message List */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 text-xs select-text">
        {messages.length === 0 ? (
          <div className="py-6 space-y-4">
            <div className="text-center space-y-1">
              <p className="font-semibold text-neutral-800 dark:text-neutral-200">
                Ask about repository architecture
              </p>
              <p className="text-[11px] text-neutral-500 dark:text-neutral-400">
                Answers use deterministic graph tools to trace dependencies, cycles, and blast radius.
              </p>
            </div>

            <div className="space-y-1.5 pt-2">
              <span className="text-[10px] font-mono uppercase tracking-wider text-neutral-400 block">
                Suggested questions:
              </span>
              {starterQuestions.map((q) => (
                <button
                  key={q}
                  type="button"
                  disabled={!isRepoReady || isStreaming}
                  onClick={() => handleSend(q)}
                  className="w-full text-left p-2.5 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white/60 dark:bg-neutral-800/40 hover:bg-orange-50/50 dark:hover:bg-orange-950/20 hover:border-orange-300 dark:hover:border-orange-800/60 text-neutral-800 dark:text-neutral-200 transition-all cursor-pointer text-xs disabled:opacity-50 disabled:cursor-not-allowed shadow-xs"
                >
                  💡 {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex flex-col ${msg.role === "user" ? "items-end" : "items-start"}`}
            >
              {msg.role === "user" ? (
                <div className="max-w-[85%] rounded-2xl rounded-tr-xs px-3.5 py-2.5 bg-orange-500 text-white shadow-xs">
                  <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                </div>
              ) : (
                <div className="w-full max-w-[95%] space-y-2">
                  {/* Tool Step Pills */}
                  {msg.steps && msg.steps.length > 0 && (
                    <div className="space-y-1">
                      {msg.steps.map((st, idx) => (
                        <details
                          key={`${st.step}-${idx}`}
                          className="group border border-neutral-200 dark:border-neutral-800 rounded-lg bg-neutral-50/80 dark:bg-neutral-800/40 text-[11px] overflow-hidden"
                        >
                          <summary className="px-2.5 py-1.5 font-medium cursor-pointer flex items-center justify-between text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-neutral-200">
                            <span className="flex items-center gap-1.5 truncate">
                              <span>{st.ok ? "🔍" : "⚠️"}</span>
                              <span className="truncate">{formatToolTitle(st)}</span>
                            </span>
                            <span className="font-mono text-[10px] text-neutral-400 ml-2">
                              {(st.duration_ms / 1000).toFixed(2)}s
                            </span>
                          </summary>
                          <div className="p-2 border-t border-neutral-200 dark:border-neutral-800 bg-white/40 dark:bg-neutral-900/40 text-[10px] font-mono space-y-1">
                            <p className="text-neutral-500">Summary: {st.summary}</p>
                            <pre className="text-neutral-700 dark:text-neutral-300 overflow-x-auto p-1 bg-neutral-100 dark:bg-neutral-800 rounded">
                              {JSON.stringify(st.args, null, 2)}
                            </pre>
                          </div>
                        </details>
                      ))}
                    </div>
                  )}

                  {/* Main content or Spinner */}
                  <div className="rounded-2xl rounded-tl-xs px-3.5 py-2.5 bg-neutral-100 dark:bg-neutral-800/80 border border-neutral-200 dark:border-neutral-700/60 shadow-xs space-y-2">
                    {msg.streaming && !msg.content ? (
                      <div className="flex items-center gap-2 text-neutral-500 dark:text-neutral-400 py-1">
                        <div className="w-3.5 h-3.5 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
                        <span className="text-[11px]">Analyzing repository topology...</span>
                      </div>
                    ) : (
                      <div className="prose prose-sm dark:prose-invert max-w-none text-xs leading-relaxed">
                        <ReactMarkdown
                          components={{
                            code: ({ children, ...props }) => {
                              const text = String(children).trim();
                              const isVerified = msg.verification?.verified_files.includes(text);
                              const isFlagged =
                                text.includes("⚠unverified") ||
                                msg.verification?.flagged.includes(
                                  text.replace(" ⚠unverified", "")
                                );

                              if (isVerified) {
                                return (
                                  <button
                                    type="button"
                                    onClick={() => handleNavigate(text)}
                                    className="inline-flex items-center font-mono text-[11px] px-1 py-0.2 rounded bg-sky-100 dark:bg-sky-900/70 text-sky-800 dark:text-sky-200 hover:underline cursor-pointer border border-sky-300 dark:border-sky-700"
                                    title={`Navigate to ${text}`}
                                  >
                                    📄 {text}
                                  </button>
                                );
                              }

                              if (isFlagged) {
                                return (
                                  <span
                                    className="inline-flex items-center gap-1 font-mono text-[11px] px-1 py-0.2 rounded bg-amber-100/80 dark:bg-amber-950/60 text-amber-800 dark:text-amber-300 border border-amber-300 dark:border-amber-700/80"
                                    title="Not found in this repository's graph"
                                  >
                                    <span>{text.replace(" ⚠unverified", "")}</span>
                                    <span className="font-bold text-amber-600 dark:text-amber-400">
                                      ⚠
                                    </span>
                                  </span>
                                );
                              }

                              return (
                                <code
                                  className="bg-neutral-200 dark:bg-neutral-700 px-1 py-0.5 rounded font-mono text-[11px]"
                                  {...props}
                                >
                                  {children}
                                </code>
                              );
                            },
                          }}
                        >
                          {msg.content}
                        </ReactMarkdown>
                      </div>
                    )}

                    {/* Verified file chips below */}
                    {msg.verification && msg.verification.verified_files.length > 0 && (
                      <div className="pt-2 border-t border-neutral-200 dark:border-neutral-700 space-y-1">
                        <span className="text-[10px] font-mono uppercase tracking-wider text-neutral-400 block">
                          Verified Files ({msg.verification.verified_files.length})
                        </span>
                        <div className="flex flex-wrap gap-1">
                          {msg.verification.verified_files.map((file) => (
                            <button
                              key={file}
                              type="button"
                              onClick={() => handleNavigate(file)}
                              className="text-[11px] font-mono px-2 py-0.5 rounded bg-sky-100/70 dark:bg-sky-900/50 text-sky-700 dark:text-sky-300 hover:bg-sky-200 dark:hover:bg-sky-800 border border-sky-300/60 dark:border-sky-800 transition-colors cursor-pointer truncate max-w-full"
                              title={`Focus ${file} on canvas`}
                            >
                              {file}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Flagged unverified files */}
                    {msg.verification && msg.verification.flagged.length > 0 && (
                      <div className="pt-1 flex flex-wrap gap-1">
                        {msg.verification.flagged.map((file) => (
                          <span
                            key={file}
                            className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800/60 inline-flex items-center gap-1"
                            title="Not found in this repository's graph"
                          >
                            <span>{file}</span>
                            <span className="text-amber-600 font-bold">⚠ unverified</span>
                          </span>
                        ))}
                      </div>
                    )}

                    {/* Error Notice */}
                    {msg.error && (
                      <div className="p-2 rounded bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 text-rose-700 dark:text-rose-300 text-[11px]">
                        ⚠️ {msg.error}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Bar */}
      <div className="p-3 border-t border-neutral-200 dark:border-neutral-800 bg-neutral-50/70 dark:bg-neutral-900/70">
        {!isRepoReady && (
          <p className="text-[11px] text-amber-600 dark:text-amber-400 mb-2">
            Repository must finish analyzing before chatting.
          </p>
        )}

        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="space-y-2"
        >
          <div className="relative">
            <textarea
              id="repo-chat-input"
              rows={2}
              value={input}
              disabled={!isRepoReady || isStreaming}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder={
                isRepoReady
                  ? "Ask about architecture, dependencies, or blast radius..."
                  : "Waiting for analysis to complete..."
              }
              className="w-full text-xs p-2.5 rounded-xl border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-orange-500/60 resize-none disabled:opacity-50 disabled:cursor-not-allowed shadow-inner"
            />
          </div>

          <div className="flex items-center justify-between">
            <span className="text-[10px] text-neutral-400">
              Shift+Enter for newline
            </span>

            <div className="flex items-center gap-1.5">
              {isStreaming ? (
                <button
                  type="button"
                  id="chat-stop-btn"
                  onClick={handleStop}
                  className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-rose-500 hover:bg-rose-600 text-white transition-all shadow-xs cursor-pointer flex items-center gap-1"
                >
                  <span>⏹</span>
                  <span>Stop</span>
                </button>
              ) : (
                <button
                  type="submit"
                  id="chat-send-btn"
                  disabled={!isRepoReady || !input.trim()}
                  className="px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-orange-500 hover:bg-orange-600 text-white transition-all shadow-xs cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1"
                >
                  <span>Send</span>
                  <span>&rarr;</span>
                </button>
              )}
            </div>
          </div>
        </form>
      </div>
    </aside>
  );
});
