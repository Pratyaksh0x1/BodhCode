import { useState, useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AUTH_QUERY_KEY, pollDesktopAuthTicket, useChatGPTLogin } from "../../lib/auth";
import { VITE_API_URL } from "../../lib/env";

interface LoginModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function LoginModal({ isOpen, onClose }: LoginModalProps) {
  const [activeTab, setActiveTab] = useState<"github" | "chatgpt">("github");
  const [isWaitingChrome, setIsWaitingChrome] = useState(false);
  const [chatgptKey, setChatgptKey] = useState("");
  const [selectedModel, setSelectedModel] = useState("gpt-4o");
  const [chatgptError, setChatgptError] = useState<string | null>(null);
  const [chatgptSubmitting, setChatgptSubmitting] = useState(false);

  const queryClient = useQueryClient();
  const chatgptLoginMutation = useChatGPTLogin();
  const pollIntervalRef = useRef<number | null>(null);

  // Clear polling on unmount or close
  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) {
        window.clearInterval(pollIntervalRef.current);
      }
    };
  }, []);

  if (!isOpen) return null;

  const handleGithubChromeLogin = () => {
    setIsWaitingChrome(true);
    const ticket = typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `tk-${Date.now()}`;
    const loginUrl = `${VITE_API_URL}/auth/github/login?ticket=${encodeURIComponent(ticket)}`;

    // Open directly in Chrome / default system browser
    window.open(loginUrl, "_blank");

    // Start polling for approval from Chrome
    if (pollIntervalRef.current) {
      window.clearInterval(pollIntervalRef.current);
    }

    pollIntervalRef.current = window.setInterval(async () => {
      try {
        const user = await pollDesktopAuthTicket(ticket);
        if (user) {
          if (pollIntervalRef.current) {
            window.clearInterval(pollIntervalRef.current);
          }
          queryClient.setQueryData(AUTH_QUERY_KEY, user);
          setIsWaitingChrome(false);
          onClose();
        }
      } catch {
        // Continue polling until timeout or close
      }
    }, 1500);
  };

  const handleChatGPTSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatgptKey.trim()) {
      setChatgptError("Please enter your OpenAI / ChatGPT API key or token.");
      return;
    }

    setChatgptSubmitting(true);
    setChatgptError(null);

    try {
      await chatgptLoginMutation({
        apiKey: chatgptKey.trim(),
        model: selectedModel,
      });
      onClose();
    } catch (err: unknown) {
      setChatgptError(err instanceof Error ? err.message : "Failed to connect ChatGPT account.");
    } finally {
      setChatgptSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-xs animate-in fade-in duration-200">
      <div className="w-full max-w-md bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 rounded-2xl shadow-2xl overflow-hidden text-neutral-900 dark:text-neutral-100">
        {/* Header */}
        <div className="px-6 py-5 border-b border-neutral-200 dark:border-neutral-800 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-lg bg-orange-500/10 dark:bg-orange-500/20 flex items-center justify-center text-orange-500 font-bold text-sm">
              BC
            </div>
            <div>
              <h2 className="text-base font-bold tracking-tight">Sign in to BodhCode Studio</h2>
              <p className="text-xs text-neutral-500 dark:text-neutral-400">
                Choose your AI Workspace Account
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-neutral-400 hover:text-neutral-200 p-1 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 cursor-pointer"
          >
            ✕
          </button>
        </div>

        {/* Tab switcher */}
        <div className="flex border-b border-neutral-200 dark:border-neutral-800 bg-neutral-50/50 dark:bg-neutral-950/40 p-1.5 gap-1.5">
          <button
            type="button"
            onClick={() => setActiveTab("github")}
            className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all flex items-center justify-center gap-2 cursor-pointer ${
              activeTab === "github"
                ? "bg-white dark:bg-neutral-800 text-orange-500 shadow-xs"
                : "text-neutral-500 hover:text-neutral-300"
            }`}
          >
            <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24">
              <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
            </svg>
            <span>GitHub (Copilot)</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("chatgpt")}
            className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all flex items-center justify-center gap-2 cursor-pointer ${
              activeTab === "chatgpt"
                ? "bg-white dark:bg-neutral-800 text-emerald-500 shadow-xs"
                : "text-neutral-500 hover:text-neutral-300"
            }`}
          >
            <span className="text-sm">⚡</span>
            <span>ChatGPT / Codex</span>
          </button>
        </div>

        {/* Content */}
        <div className="p-6">
          {activeTab === "github" ? (
            <div className="space-y-4">
              <div className="p-4 rounded-xl bg-neutral-100 dark:bg-neutral-800/60 border border-neutral-200 dark:border-neutral-700/60 text-xs space-y-2">
                <p className="font-semibold text-neutral-800 dark:text-neutral-200 flex items-center gap-1.5">
                  <span>🐙</span> Connect GitHub &amp; Copilot
                </p>
                <p className="text-neutral-500 dark:text-neutral-400 leading-relaxed">
                  Authenticates with your GitHub account in Google Chrome to enable GitHub Copilot code editing, repository imports, and verified Git commits.
                </p>
              </div>

              {isWaitingChrome ? (
                <div className="py-6 flex flex-col items-center justify-center text-center space-y-3 bg-orange-500/5 dark:bg-orange-500/10 rounded-xl border border-orange-500/30">
                  <div className="w-7 h-7 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
                  <div className="space-y-1">
                    <p className="text-xs font-semibold text-orange-500">
                      Redirected to Google Chrome...
                    </p>
                    <p className="text-[11px] text-neutral-400 max-w-xs">
                      Please complete the authorization in Chrome. This window will automatically update once verified.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      if (pollIntervalRef.current) window.clearInterval(pollIntervalRef.current);
                      setIsWaitingChrome(false);
                    }}
                    className="text-xs text-neutral-400 hover:text-neutral-200 underline cursor-pointer mt-1"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  id="modal-github-login-btn"
                  onClick={handleGithubChromeLogin}
                  className="w-full py-2.5 px-4 rounded-xl bg-orange-500 hover:bg-orange-600 text-white text-xs font-semibold transition-all shadow-md shadow-orange-500/20 flex items-center justify-center gap-2 cursor-pointer hover:scale-[1.01] active:scale-[0.99]"
                >
                  <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24">
                    <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
                  </svg>
                  <span>Open Chrome &amp; Login with GitHub</span>
                </button>
              )}
            </div>
          ) : (
            <form onSubmit={handleChatGPTSubmit} className="space-y-4">
              <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-xs space-y-2">
                <p className="font-semibold text-emerald-400 flex items-center gap-1.5">
                  <span>⚡</span> Connect OpenAI Codex &amp; ChatGPT
                </p>
                <p className="text-neutral-400 leading-relaxed">
                  Enables Codex &amp; ChatGPT in your Code Editor for automated project building, complex feature implementation, and architecture assistance.
                </p>
              </div>

              {chatgptError && (
                <div className="p-2.5 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">
                  {chatgptError}
                </div>
              )}

              <div className="space-y-1.5">
                <label
                  htmlFor="chatgpt-key-input"
                  className="block text-xs font-semibold text-neutral-300"
                >
                  OpenAI / ChatGPT API Key or Token
                </label>
                <input
                  id="chatgpt-key-input"
                  type="password"
                  value={chatgptKey}
                  onChange={(e) => setChatgptKey(e.target.value)}
                  placeholder="sk-proj-... or ChatGPT session token"
                  className="w-full px-3 py-2 text-xs rounded-xl bg-neutral-100 dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-700 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 font-mono text-neutral-100"
                />
              </div>

              <div className="space-y-1.5">
                <label
                  htmlFor="chatgpt-model-select"
                  className="block text-xs font-semibold text-neutral-300"
                >
                  Codex / ChatGPT Default Model
                </label>
                <select
                  id="chatgpt-model-select"
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                  className="w-full px-3 py-2 text-xs rounded-xl bg-neutral-100 dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-700 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 text-neutral-100"
                >
                  <option value="gpt-4o">gpt-4o (Recommended - Multimodal &amp; Code)</option>
                  <option value="gpt-4o-mini">gpt-4o-mini (Fast &amp; Efficient)</option>
                  <option value="o1-preview">o1-preview (Deep Reasoning)</option>
                  <option value="o3-mini">o3-mini (High-speed STEM reasoning)</option>
                </select>
              </div>

              <div className="flex items-center justify-between pt-1">
                <a
                  href="https://platform.openai.com/api-keys"
                  target="_blank"
                  rel="noreferrer"
                  className="text-[11px] text-emerald-400 hover:underline flex items-center gap-1"
                >
                  <span>Get OpenAI key in Chrome &rarr;</span>
                </a>

                <button
                  type="submit"
                  disabled={chatgptSubmitting || !chatgptKey.trim()}
                  className="py-2 px-4 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold transition-all shadow-md shadow-emerald-600/20 flex items-center gap-1.5 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {chatgptSubmitting ? (
                    <>
                      <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      <span>Connecting...</span>
                    </>
                  ) : (
                    <span>Connect Codex &amp; ChatGPT</span>
                  )}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
