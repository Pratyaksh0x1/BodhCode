import { Link, useParams } from "react-router-dom";
import { useRepo } from "../lib/repos";

export function RepoDetail() {
  const { id } = useParams<{ id: string }>();
  const { data: repo, isLoading, isError, error } = useRepo(id);

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
        <Link to="/" className="text-sm text-sky-400 hover:text-sky-300 inline-flex items-center gap-1.5">
          &larr; Back to repositories
        </Link>
        <div className="p-6 rounded-2xl bg-rose-950/30 border border-rose-900/50 text-rose-300 space-y-2">
          <h2 className="text-base font-semibold text-rose-200">Repository Not Found</h2>
          <p className="text-sm">{error?.message || "Failed to load repository."}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Breadcrumb Navigation */}
      <div className="flex items-center gap-2 text-xs font-mono text-slate-500">
        <Link to="/" className="text-slate-400 hover:text-slate-200 transition-colors">
          Repositories
        </Link>
        <span>/</span>
        <span className="text-slate-200">{repo.owner}</span>
        <span>/</span>
        <span className="text-sky-400 font-bold">{repo.name}</span>
      </div>

      {/* Repo Title Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-slate-800">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight text-slate-100 flex items-center gap-2">
            <span>{repo.owner}</span>
            <span className="text-slate-600">/</span>
            <span className="text-sky-300">{repo.name}</span>
          </h1>
          <p className="text-sm text-slate-400 font-mono mt-1">
            branch <span className="text-slate-200">{repo.branch}</span>
            {repo.commit_sha && (
              <span className="ml-2 text-slate-500">
                @ <span className="text-indigo-400">{repo.commit_sha.slice(0, 7)}</span>
              </span>
            )}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <span
            className={`px-3 py-1 rounded-full text-xs font-medium border ${
              repo.status === "fetched"
                ? "bg-emerald-950 text-emerald-300 border-emerald-800"
                : repo.status === "failed"
                ? "bg-rose-950 text-rose-300 border-rose-800"
                : "bg-sky-950 text-sky-300 border-sky-800"
            }`}
          >
            {repo.status.toUpperCase()}
          </span>
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

      {/* Ingestion Failed State */}
      {repo.status === "failed" && (
        <div className="p-6 rounded-2xl border border-rose-900/50 bg-rose-950/20 space-y-3">
          <h2 className="text-base font-semibold text-rose-200">Repository Ingestion Failed</h2>
          <p className="text-sm text-rose-300 font-mono bg-black/40 p-3 rounded border border-rose-900/30">
            {repo.error_message || "An unknown error occurred during ingestion."}
          </p>
          <Link
            to="/"
            className="inline-block text-xs font-medium px-3 py-1.5 rounded bg-rose-900/40 hover:bg-rose-800/40 border border-rose-700/50 text-rose-200 transition-colors"
          >
            Return to Dashboard
          </Link>
        </div>
      )}

      {/* Ingestion Fetched Success State */}
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
              <span className="text-xs text-slate-500 block mb-1">Status</span>
              <span className="text-sm font-bold font-mono text-emerald-400">READY</span>
            </div>
          </div>

          <div className="p-12 rounded-2xl border border-slate-800 bg-slate-900/30 text-center space-y-3">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-slate-800 bg-slate-900 text-xs font-mono text-slate-400">
              <span>Phase 4 Workspace Target</span>
            </div>
            <h3 className="text-lg font-semibold text-slate-200">
              Dependency Graph &amp; AST Blast Radius Visualizer
            </h3>
            <p className="text-sm text-slate-400 max-w-lg mx-auto">
              Tree-sitter AST extraction, symbol dependency mapping, and React Flow visualizer will be activated here in Phase 4.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
