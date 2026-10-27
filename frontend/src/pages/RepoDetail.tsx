import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAnalyzeRepo, useRepo, useRepoGraph } from "../lib/repos";
import { RepoCanvas } from "../components/canvas/RepoCanvas";

export function RepoDetail() {
  const { id } = useParams<{ id: string }>();
  const { data: repo, isLoading, isError, error } = useRepo(id);
  const analyzeMutation = useAnalyzeRepo();

  const [activeTab, setActiveTab] = useState<"map" | "readme" | "issues" | "prs">("map");

  const isReady = repo?.status === "ready";
  const { data: graph, isLoading: isGraphLoading } = useRepoGraph(repo?.id, isReady);

  if (isLoading) {
    return (
      <div className="py-12 flex flex-col items-center justify-center gap-3 text-slate-400">
        <div className="w-8 h-8 border-2 border-sky-400 border-t-transparent rounded-full animate-spin" />
        <p className="text-sm">Loading repository details...</p>
      </div>
    );
  }

  if (isError || !repo) {
    return (
      <div className="space-y-4">
        <Link
          to="/"
          className="text-sm text-orange-400 hover:text-orange-300 inline-flex items-center gap-1.5"
        >
          &larr; Back to repositories
        </Link>
        <div className="p-6 rounded-2xl bg-rose-950/30 border border-rose-900/50 text-rose-300 space-y-2">
          <h2 className="text-base font-semibold text-rose-200">Repository Not Found</h2>
          <p className="text-sm">{error?.message || "Failed to load repository."}</p>
        </div>
      </div>
    );
  }

  const getStatusBadgeClass = () => {
    switch (repo.status) {
      case "ready":
        return "bg-emerald-950 text-emerald-300 border-emerald-800";
      case "analyzing":
        return "bg-violet-950 text-violet-300 border-violet-800 animate-pulse";
      case "fetched":
        return "bg-sky-950 text-sky-300 border-sky-800";
      case "failed":
        return "bg-rose-950 text-rose-300 border-rose-800";
      default:
        return "bg-amber-950 text-amber-300 border-amber-800";
    }
  };

  return (
    <div className="space-y-8">
      {/* Breadcrumb Navigation */}
      <div className="flex items-center gap-2 text-xs font-mono text-neutral-500">
        <Link to="/" className="text-neutral-400 hover:text-neutral-200 transition-colors">
          Repositories
        </Link>
        <span>/</span>
        <span className="text-neutral-200">{repo.owner}</span>
        <span>/</span>
        <span className="text-orange-400 font-bold">{repo.name}</span>
      </div>

      {/* Repo Title Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-neutral-800">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight text-neutral-100 flex items-center gap-2">
            <span>{repo.owner}</span>
            <span className="text-neutral-600">/</span>
            <span className="text-orange-400">{repo.name}</span>
          </h1>
          <p className="text-sm text-neutral-400 font-mono mt-1">
            branch <span className="text-neutral-200">{repo.branch}</span>
            {repo.commit_sha && (
              <span className="ml-2 text-neutral-500">
                @ <span className="text-neutral-300">{repo.commit_sha.slice(0, 7)}</span>
              </span>
            )}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <span className={`px-3 py-1 rounded-full text-xs font-medium border ${getStatusBadgeClass()}`}>
            {repo.status.toUpperCase()}
          </span>

          {repo.status === "fetched" && (
            <button
              onClick={() => analyzeMutation.mutate(repo.id)}
              disabled={analyzeMutation.isPending}
              className="px-4 py-1.5 rounded-lg text-xs font-semibold bg-orange-500 hover:bg-orange-400 text-white transition-colors flex items-center gap-2 cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {analyzeMutation.isPending ? (
                <>
                  <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  <span>Starting...</span>
                </>
              ) : (
                <span>Analyze</span>
              )}
            </button>
          )}

          {repo.status === "ready" && (
            <button
              onClick={() => analyzeMutation.mutate(repo.id)}
              disabled={analyzeMutation.isPending}
              className="px-3 py-1 rounded-lg text-xs font-medium border border-neutral-700 bg-neutral-800 hover:bg-neutral-700 text-neutral-300 transition-colors cursor-pointer disabled:opacity-60"
            >
              Re-analyze
            </button>
          )}
        </div>
      </div>

      {/* Ingestion In Progress State */}
      {(repo.status === "queued" || repo.status === "fetching") && (
        <div className="p-12 rounded-2xl border border-sky-900/40 bg-sky-950/20 text-center space-y-4">
          <div className="w-10 h-10 border-3 border-sky-400 border-t-transparent rounded-full animate-spin mx-auto" />
          <h2 className="text-lg font-semibold text-slate-100">
            {repo.status === "queued" ? "Waiting in ingestion queue..." : "Fetching and extracting repository source..."}
          </h2>
          <p className="text-sm text-slate-400 max-w-md mx-auto">
            BodhCode is streaming the zipball from GitHub and verifying file safety constraints. This page will update automatically.
          </p>
        </div>
      )}

      {/* Analyzing In Progress State */}
      {repo.status === "analyzing" && (
        <div className="p-12 rounded-2xl border border-violet-900/40 bg-violet-950/20 text-center space-y-4">
          <div className="w-10 h-10 border-3 border-violet-400 border-t-transparent rounded-full animate-spin mx-auto" />
          <h2 className="text-lg font-semibold text-slate-100">
            Analyzing repository dependencies...
          </h2>
          <p className="text-sm text-slate-400 max-w-md mx-auto">
            Parsing TypeScript/JavaScript ASTs with tree-sitter, mapping module imports, and computing blast radius impacts.
          </p>
        </div>
      )}

      {/* Ingestion/Analysis Failed State */}
      {repo.status === "failed" && (
        <div className="p-6 rounded-2xl border border-rose-900/50 bg-rose-950/20 space-y-3">
          <h2 className="text-base font-semibold text-rose-200">Repository Processing Failed</h2>
          <p className="text-sm text-rose-300 font-mono bg-black/40 p-3 rounded border border-rose-900/30">
            {repo.error_message || "An error occurred during repository ingestion or analysis."}
          </p>
          <div className="flex items-center gap-3 pt-2">
            <button
              onClick={() => analyzeMutation.mutate(repo.id)}
              disabled={analyzeMutation.isPending}
              className="inline-block text-xs font-medium px-3 py-1.5 rounded bg-rose-900/40 hover:bg-rose-800/40 border border-rose-700/50 text-rose-200 transition-colors cursor-pointer"
            >
              Retry Analysis
            </button>
            <Link
              to="/"
              className="inline-block text-xs font-medium px-3 py-1.5 rounded bg-neutral-800 hover:bg-neutral-700 border border-neutral-700 text-neutral-300 transition-colors"
            >
              Return to Dashboard
            </Link>
          </div>
        </div>
      )}

      {/* Fetched State (Ready for Analysis) */}
      {repo.status === "fetched" && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/40">
              <span className="text-xs text-slate-500 block mb-1">Source Files</span>
              <span className="text-xl font-bold font-mono text-slate-100">{repo.file_count ?? 0}</span>
            </div>
            <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/40">
              <span className="text-xs text-slate-500 block mb-1">Repository Size</span>
              <span className="text-xl font-bold font-mono text-slate-100">
                {repo.default_branch_size_kb ? `${repo.default_branch_size_kb} KB` : "N/A"}
              </span>
            </div>
            <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/40">
              <span className="text-xs text-slate-500 block mb-1">Head Commit</span>
              <span className="text-sm font-bold font-mono text-indigo-400">
                {repo.commit_sha ? repo.commit_sha.slice(0, 10) : "N/A"}
              </span>
            </div>
            <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/40">
              <span className="text-xs text-slate-500 block mb-1">Ingestion</span>
              <span className="text-sm font-bold font-mono text-emerald-400">COMPLETE</span>
            </div>
          </div>

          <div className="p-8 rounded-2xl border border-orange-900/40 bg-orange-950/20 text-center space-y-4">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-orange-800/50 bg-orange-900/30 text-xs font-mono text-orange-300">
              <span>Ready for Analysis</span>
            </div>
            <h3 className="text-lg font-semibold text-slate-200">
              Build Dependency Graph &amp; Blast Radius
            </h3>
            <p className="text-sm text-slate-400 max-w-lg mx-auto">
              Extract semantic import/export facts, detect dependency cycles, and compute blast radius for each source file.
            </p>
            <button
              onClick={() => analyzeMutation.mutate(repo.id)}
              disabled={analyzeMutation.isPending}
              className="px-6 py-2.5 rounded-xl font-semibold text-sm bg-gradient-to-r from-orange-500 to-amber-500 hover:from-orange-400 hover:to-amber-400 text-white shadow-lg shadow-orange-950/40 transition-all cursor-pointer inline-flex items-center gap-2 disabled:opacity-60"
            >
              {analyzeMutation.isPending ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  <span>Starting Analysis...</span>
                </>
              ) : (
                <>
                  <span>Analyze Repository</span>
                  <span>&rarr;</span>
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* Ready State: Shows Canonical Graph Canvas with Tabs */}
      {repo.status === "ready" && (
        <div className="space-y-4">
          {/* Tabs Scaffold */}
          <div className="flex items-center gap-1 border-b border-neutral-200 dark:border-neutral-800 text-xs">
            <button
              type="button"
              onClick={() => setActiveTab("map")}
              aria-selected={activeTab === "map"}
              className={`px-4 py-2 font-semibold border-b-2 flex items-center gap-2 transition-colors cursor-pointer ${
                activeTab === "map"
                  ? "border-orange-500 text-orange-500 dark:text-orange-400"
                  : "border-transparent text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300"
              }`}
            >
              <span>Map</span>
              <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-orange-500/10 text-orange-500 dark:text-orange-400 font-mono">
                Interactive
              </span>
            </button>

            <button
              type="button"
              disabled
              title="Available in Phase 9"
              className="px-4 py-2 font-medium text-neutral-400 dark:text-neutral-600 cursor-not-allowed flex items-center gap-1.5"
            >
              <span>README</span>
              <span className="text-[9px] px-1 rounded bg-neutral-200 dark:bg-neutral-800 text-neutral-400 dark:text-neutral-500">
                Soon
              </span>
            </button>

            <button
              type="button"
              disabled
              title="Available in Phase 9"
              className="px-4 py-2 font-medium text-neutral-400 dark:text-neutral-600 cursor-not-allowed flex items-center gap-1.5"
            >
              <span>Issues</span>
              <span className="text-[9px] px-1 rounded bg-neutral-200 dark:bg-neutral-800 text-neutral-400 dark:text-neutral-500">
                Soon
              </span>
            </button>

            <button
              type="button"
              disabled
              title="Available in Phase 9"
              className="px-4 py-2 font-medium text-neutral-400 dark:text-neutral-600 cursor-not-allowed flex items-center gap-1.5"
            >
              <span>Pull Requests</span>
              <span className="text-[9px] px-1 rounded bg-neutral-200 dark:bg-neutral-800 text-neutral-400 dark:text-neutral-500">
                Soon
              </span>
            </button>
          </div>

          {/* Active Tab Content */}
          {activeTab === "map" && (
            <div>
              {isGraphLoading || !graph ? (
                <div className="py-24 flex flex-col items-center justify-center gap-3 text-neutral-400 rounded-2xl border border-neutral-800 bg-neutral-900/30">
                  <div className="w-8 h-8 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
                  <p className="text-sm">Loading repository dependency graph...</p>
                </div>
              ) : (
                <RepoCanvas repoId={repo.id} graph={graph} />
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
