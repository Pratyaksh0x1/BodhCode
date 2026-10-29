import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMe } from "../lib/auth";
import { VITE_API_URL } from "../lib/env";
import { useCreateLocalWorkspace, useCreateRepo, useDeleteRepo, useRefreshRepo, useRepos, validateRepoUrl, type Repo } from "../lib/repos";

function formatRelativeTime(isoString: string): string {
  try {
    const date = new Date(isoString);
    const now = new Date();
    const diffSec = Math.floor((now.getTime() - date.getTime()) / 1000);
    if (diffSec < 10) return "just now";
    if (diffSec < 60) return `${diffSec}s ago`;
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHours = Math.floor(diffMin / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays}d ago`;
  } catch {
    return isoString;
  }
}

export function Home() {
  const { data: user, isLoading: isUserLoading } = useMe();
  const { data: repos, isLoading: isReposLoading } = useRepos();
  const createRepo = useCreateRepo();
  const refreshRepo = useRefreshRepo();
  const deleteRepo = useDeleteRepo();
  const createLocalWorkspace = useCreateLocalWorkspace();
  const navigate = useNavigate();

  const handleCreateNewProject = () => {
    createLocalWorkspace.mutate(undefined, {
      onSuccess: (newRepo) => {
        navigate(`/repos/${newRepo.id}/editor`);
      },
    });
  };

  const [inputUrl, setInputUrl] = useState("");
  const [clientValidationError, setClientValidationError] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);

  const handleInputChange = (val: string) => {
    setInputUrl(val);
    if (clientValidationError) {
      setClientValidationError(null);
    }
  };

  const handleInputBlur = () => {
    if (!inputUrl.trim()) {
      setClientValidationError(null);
      return;
    }
    try {
      validateRepoUrl(inputUrl);
      setClientValidationError(null);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setClientValidationError(err.message);
      }
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = inputUrl.trim();
    if (!trimmed) {
      setClientValidationError("Please enter a GitHub repository link or shorthand.");
      return;
    }

    try {
      validateRepoUrl(trimmed);
      setClientValidationError(null);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setClientValidationError(err.message);
      }
      return;
    }

    createRepo.mutate(trimmed, {
      onSuccess: () => {
        setInputUrl("");
        setClientValidationError(null);
      },
    });
  };

  // Signed-out Hero State
  if (!isUserLoading && !user) {
    return (
      <div className="py-12 px-4 max-w-4xl mx-auto space-y-12 text-center">
        <div className="space-y-6">
          <div className="inline-flex items-center gap-3 px-4 py-1.5 rounded-full border border-orange-500/30 bg-orange-950/30 text-orange-300 text-xs font-medium tracking-wide">
            <span className="w-2 h-2 rounded-full bg-orange-400 animate-ping" />
            Deterministic AST Dependency Graphs
          </div>

          <h1 className="text-4xl sm:text-6xl font-extrabold tracking-tight text-neutral-100 leading-tight">
            Understand any codebase{" "}
            <span className="bg-gradient-to-r from-orange-400 via-amber-200 to-yellow-400 bg-clip-text text-transparent">
              with mathematical precision
            </span>
          </h1>

          <p className="max-w-2xl mx-auto text-lg text-neutral-400 leading-relaxed">
            BodhCode turns TypeScript and JavaScript repositories into interactive dependency maps,
            explains architectural blast radius in your language, and enables verified in-browser code editing.
          </p>

          <div className="pt-4 flex flex-col sm:flex-row items-center justify-center gap-4">
            <a
              id="hero-github-login-btn"
              href={`${VITE_API_URL}/auth/github/login`}
              className="flex items-center justify-center gap-3 px-8 py-3.5 rounded-xl bg-orange-500 hover:bg-orange-600 text-white font-semibold shadow-lg shadow-orange-500/25 transition-all hover:scale-[1.02] active:scale-[0.98]"
            >
              <svg className="w-5 h-5 fill-current" viewBox="0 0 24 24">
                <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
              </svg>
              <span>Sign in with GitHub</span>
            </a>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-8 text-left">
          <div className="p-6 rounded-2xl border border-neutral-800 bg-neutral-900/50 backdrop-blur">
            <div className="w-10 h-10 rounded-xl bg-neutral-800 border border-neutral-700 flex items-center justify-center text-orange-400 mb-4 font-bold">
              1
            </div>
            <h3 className="text-base font-semibold text-neutral-200 mb-1">Safe Zip Ingestion</h3>
            <p className="text-sm text-neutral-400 leading-relaxed">
              Fetches public repositories with streaming extraction, zip-bomb mitigation, and path traversal defense.
            </p>
          </div>

          <div className="p-6 rounded-2xl border border-neutral-800 bg-neutral-900/50 backdrop-blur">
            <div className="w-10 h-10 rounded-xl bg-neutral-800 border border-neutral-700 flex items-center justify-center text-orange-400 mb-4 font-bold">
              2
            </div>
            <h3 className="text-base font-semibold text-neutral-200 mb-1">Tree-Sitter Parsing</h3>
            <p className="text-sm text-neutral-400 leading-relaxed">
              Extracts symbols, exports, and call graphs using pure grammar engines — zero LLM hallucination in topology.
            </p>
          </div>

          <div className="p-6 rounded-2xl border border-neutral-800 bg-neutral-900/50 backdrop-blur">
            <div className="w-10 h-10 rounded-xl bg-neutral-800 border border-neutral-700 flex items-center justify-center text-orange-400 mb-4 font-bold">
              3
            </div>
            <h3 className="text-base font-semibold text-neutral-200 mb-1">Interactive Blast Radius</h3>
            <p className="text-sm text-neutral-400 leading-relaxed">
              Explore your code visually, calculate exact change impacts, and propose verified pull requests.
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Signed-in Dashboard
  return (
    <div className="space-y-10">
      {/* Studio Quick Launch Hero Card */}
      <section className="p-6 rounded-2xl bg-gradient-to-r from-orange-500/15 via-amber-500/10 to-neutral-900/40 border border-orange-500/30 flex flex-col md:flex-row items-start md:items-center justify-between gap-5 shadow-xl">
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold font-mono uppercase bg-orange-500/20 text-orange-400 border border-orange-500/40">
              ⚡ Unified AI IDE Studio
            </span>
            <span className="text-xs text-neutral-400 font-mono">VS Code OSS &bull; Codex &bull; AST Topology</span>
          </div>
          <h2 className="text-2xl font-bold tracking-tight text-neutral-100">
            Open Code Editor &amp; AI Studio
          </h2>
          <p className="text-sm text-neutral-300 max-w-xl leading-relaxed">
            Create files, run CLI terminal commands, edit with Monaco, and build projects powered by ChatGPT and Copilot AI agents.
          </p>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <Link
            to="/editor"
            id="hero-open-editor-btn"
            className="px-5 py-2.5 rounded-xl text-sm font-semibold bg-gradient-to-r from-orange-500 to-amber-500 hover:from-orange-400 hover:to-amber-400 text-white shadow-lg shadow-orange-500/30 flex items-center gap-2 transition-all hover:scale-105 active:scale-95"
          >
            <span>💻</span>
            <span>Open Code Editor</span>
          </Link>
          <button
            type="button"
            id="hero-new-project-btn"
            onClick={handleCreateNewProject}
            disabled={createLocalWorkspace.isPending}
            className="px-4 py-2.5 rounded-xl text-sm font-medium border border-neutral-700 bg-neutral-800 hover:bg-neutral-700 text-neutral-200 transition-colors flex items-center gap-2 cursor-pointer disabled:opacity-50"
          >
            <span>✨</span>
            <span>{createLocalWorkspace.isPending ? "Creating..." : "New Local Project"}</span>
          </button>
        </div>
      </section>

      {/* Repo Input Section */}
      <section className="space-y-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-neutral-100">Analyze Repository</h1>
          <p className="text-sm text-neutral-400 mt-1">
            Paste a public GitHub repository link or shorthand to inspect its architecture.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <label htmlFor="repo-url-input" className="sr-only">
                GitHub Repository URL
              </label>
              <input
                id="repo-url-input"
                type="text"
                value={inputUrl}
                onChange={(e) => handleInputChange(e.target.value)}
                onBlur={handleInputBlur}
                placeholder="e.g. https://github.com/facebook/react or facebook/react"
                className="w-full px-4 py-3 rounded-xl bg-neutral-900 border border-neutral-800 text-neutral-100 placeholder-neutral-500 focus:outline-none focus:ring-2 focus:ring-orange-500/50 focus:border-orange-500 text-sm font-mono transition-all"
                disabled={createRepo.isPending}
              />
            </div>
            <button
              id="analyze-repo-btn"
              type="submit"
              disabled={createRepo.isPending || !inputUrl.trim()}
              className="px-6 py-3 rounded-xl bg-orange-500 hover:bg-orange-600 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold text-sm transition-all shadow-md shadow-orange-500/20 flex items-center justify-center gap-2 shrink-0 hover:scale-[1.01] active:scale-[0.99]"
            >
              {createRepo.isPending ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span>Adding...</span>
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                  <span>Analyze</span>
                </>
              )}
            </button>
          </div>

          {clientValidationError && (
            <p id="repo-url-validation-error" className="text-xs text-rose-400 flex items-center gap-1.5 font-medium">
              <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              {clientValidationError}
            </p>
          )}

          {createRepo.isError && (
            <div
              id="create-repo-error-banner"
              className="p-3.5 rounded-lg bg-rose-950/40 border border-rose-800/60 text-rose-300 text-sm flex items-center justify-between"
            >
              <span>{createRepo.error.message}</span>
              <button
                type="button"
                onClick={() => createRepo.reset()}
                className="text-rose-400 hover:text-rose-200 text-xs px-2 py-0.5 rounded"
              >
                Dismiss
              </button>
            </div>
          )}
        </form>
      </section>

      {/* Repositories List Section */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-bold tracking-tight text-slate-100">Your Repositories</h2>
            {repos && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700">
                {repos.length}
              </span>
            )}
          </div>
        </div>

        {isReposLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[1, 2].map((i) => (
              <div key={i} className="p-6 rounded-2xl border border-slate-800 bg-slate-900/30 animate-pulse h-40" />
            ))}
          </div>
        ) : !repos || repos.length === 0 ? (
          <div
            id="empty-repos-state"
            className="p-12 rounded-2xl border border-dashed border-slate-800 bg-slate-900/20 text-center space-y-2"
          >
            <p className="text-slate-300 font-medium">No repositories analyzed yet.</p>
            <p className="text-sm text-slate-500">Paste a link above to get started.</p>
          </div>
        ) : (
          <div id="repos-grid" className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {repos.map((repo) => (
              <RepoCard
                key={repo.id}
                repo={repo}
                confirmDeleteId={confirmDeleteId}
                setConfirmDeleteId={setConfirmDeleteId}
                onRefresh={(id) => refreshRepo.mutate(id)}
                onDelete={(id) => deleteRepo.mutate(id)}
                isRefreshing={refreshRepo.isPending}
                isDeleting={deleteRepo.isPending}
                onNavigate={(id) => navigate(`/repos/${id}`)}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

interface RepoCardProps {
  repo: Repo;
  confirmDeleteId: number | null;
  setConfirmDeleteId: (id: number | null) => void;
  onRefresh: (id: number) => void;
  onDelete: (id: number) => void;
  isRefreshing: boolean;
  isDeleting: boolean;
  onNavigate: (id: number) => void;
}

function RepoCard({
  repo,
  confirmDeleteId,
  setConfirmDeleteId,
  onRefresh,
  onDelete,
  isRefreshing,
  isDeleting,
  onNavigate,
}: RepoCardProps) {
  const isConfirmingDelete = confirmDeleteId === repo.id;
  const isBusy = repo.status === "queued" || repo.status === "fetching" || repo.status === "analyzing";
  const isReady = repo.status === "ready" || repo.status === "fetched";

  const handleCardClick = () => {
    if (isReady) {
      onNavigate(repo.id);
    }
  };

  return (
    <div
      id={`repo-card-${repo.id}`}
      onClick={handleCardClick}
      className={`relative p-5 rounded-2xl border transition-all flex flex-col justify-between ${
        isReady
          ? "border-slate-800 hover:border-slate-700 bg-slate-900/50 hover:bg-slate-900/80 cursor-pointer shadow-lg hover:shadow-sky-500/5"
          : "border-slate-800/80 bg-slate-900/30"
      }`}
    >
      <div className="space-y-3">
        {/* Card Header: Owner / Name and Status Badge */}
        <div className="flex items-start justify-between gap-2">
          <div>
            <h3 className="font-semibold text-slate-100 text-base leading-snug flex items-center gap-1.5">
              <span>{repo.owner}</span>
              <span className="text-slate-500">/</span>
              <span className="text-orange-400 font-bold">{repo.name}</span>
            </h3>
            <p className="text-xs text-neutral-400 font-mono mt-0.5">
              {repo.branch}
              {repo.commit_sha && (
                <span className="text-neutral-500 ml-1.5">
                  @ <span className="text-neutral-300">{repo.commit_sha.slice(0, 7)}</span>
                </span>
              )}
            </p>
          </div>

          <StatusBadge repo={repo} />
        </div>

        {/* Failed error message banner */}
        {repo.status === "failed" && repo.error_message && (
          <div className="p-2.5 rounded-lg bg-rose-950/40 border border-rose-900/50 text-rose-300 text-xs">
            <span className="font-semibold">Error: </span>
            {repo.error_message}
          </div>
        )}

        {/* Ready stats (file count & size) */}
        {repo.status === "fetched" && (
          <div className="flex items-center gap-4 text-xs text-neutral-400 font-mono pt-1">
            <div>
              <span className="text-neutral-500">Files: </span>
              <span className="text-neutral-200 font-medium">{repo.file_count ?? 0}</span>
            </div>
            <div>
              <span className="text-neutral-500">Size: </span>
              <span className="text-neutral-200 font-medium">
                {repo.default_branch_size_kb ? `${repo.default_branch_size_kb} KB` : "N/A"}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Card Footer: Timestamp & Actions */}
      <div className="mt-4 pt-3 border-t border-neutral-800/80 flex items-center justify-between text-xs">
        <span className="text-neutral-500">Updated {formatRelativeTime(repo.updated_at)}</span>

        <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
          {isReady && (
            <>
              <Link
                to={`/repos/${repo.id}/editor`}
                id={`open-editor-${repo.id}`}
                className="px-3 py-1 rounded-md bg-gradient-to-r from-orange-500 to-amber-500 hover:from-orange-400 hover:to-amber-400 text-white font-semibold transition-all shadow-sm flex items-center gap-1.5"
                title="Open in BodhCode VS Code Studio"
              >
                <span>💻</span>
                <span>Open Studio Editor</span>
              </Link>
              <Link
                to={`/repos/${repo.id}`}
                id={`open-map-${repo.id}`}
                className="px-2.5 py-1 rounded-md border border-neutral-700 bg-neutral-800 hover:bg-neutral-700 text-neutral-300 font-medium transition-colors"
                title="View Dependency Map Canvas"
              >
                <span>🗺️</span>
                <span>Map</span>
              </Link>
            </>
          )}

          <button
            id={`refresh-repo-${repo.id}`}
            type="button"
            disabled={isBusy || isRefreshing}
            onClick={() => onRefresh(repo.id)}
            aria-label={`Refresh ${repo.name}`}
            className="p-1 rounded-md text-slate-400 hover:text-slate-200 hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            title="Refresh repository"
          >
            <svg
              className={`w-4 h-4 ${isBusy ? "animate-spin" : ""}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>

          {isConfirmingDelete ? (
            <div className="flex items-center gap-1.5">
              <button
                id={`confirm-delete-${repo.id}`}
                type="button"
                disabled={isDeleting}
                onClick={() => {
                  onDelete(repo.id);
                  setConfirmDeleteId(null);
                }}
                className="px-2 py-0.5 rounded bg-rose-600 hover:bg-rose-500 text-white font-medium text-xs transition-colors"
              >
                Confirm
              </button>
              <button
                type="button"
                onClick={() => setConfirmDeleteId(null)}
                className="text-slate-400 hover:text-slate-200 px-1 text-xs"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              id={`delete-repo-${repo.id}`}
              type="button"
              disabled={isDeleting}
              onClick={() => setConfirmDeleteId(repo.id)}
              aria-label={`Delete ${repo.name}`}
              className="p-1 rounded-md text-slate-500 hover:text-rose-400 hover:bg-rose-950/30 transition-colors"
              title="Delete repository"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function StatusBadge({ repo }: { repo: Repo }) {
  if (repo.status === "queued") {
    return (
      <span
        aria-live="polite"
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-slate-800 text-slate-300 border border-slate-700 shrink-0"
      >
        <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-pulse" />
        Queued
      </span>
    );
  }

  if (repo.status === "fetching") {
    return (
      <span
        aria-live="polite"
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-sky-950 text-sky-300 border border-sky-800 shrink-0"
      >
        <div className="w-2.5 h-2.5 border-2 border-sky-400/40 border-t-sky-400 rounded-full animate-spin" />
        Downloading &amp; checking...
      </span>
    );
  }

  if (repo.status === "analyzing") {
    return (
      <span
        aria-live="polite"
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-950 text-amber-300 border border-amber-800 shrink-0"
      >
        <div className="w-2.5 h-2.5 border-2 border-amber-400/40 border-t-amber-400 rounded-full animate-spin" />
        Analyzing AST...
      </span>
    );
  }

  if (repo.status === "ready" || repo.status === "fetched") {
    return (
      <span
        aria-live="polite"
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-950 text-emerald-300 border border-emerald-800 shrink-0"
      >
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
        Ready
      </span>
    );
  }

  return (
    <span
      aria-live="assertive"
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-rose-950 text-rose-300 border border-rose-800 shrink-0"
    >
      <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
      Failed
    </span>
  );
}
