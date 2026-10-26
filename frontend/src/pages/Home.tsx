import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";

interface HealthResponse {
  status: string;
  env: string;
}

export function Home() {
  const { data, isLoading, isError, error, refetch } = useQuery<HealthResponse, Error>({
    queryKey: ["health"],
    queryFn: () => api<HealthResponse>("/health"),
    retry: 1,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-100">System Diagnostics</h1>
        <p className="text-sm text-slate-400 mt-1">
          Phase 1 scaffold status and backend communication check.
        </p>
      </div>

      {isLoading && (
        <div
          id="health-loading"
          className="p-6 rounded-lg border border-slate-800 bg-slate-900/50 flex items-center gap-3 text-slate-300"
        >
          <div className="w-4 h-4 border-2 border-sky-400 border-t-transparent rounded-full animate-spin" />
          <span>Connecting to backend at <code>/health</code>...</span>
        </div>
      )}

      {isError && (
        <div
          id="health-error"
          className="p-6 rounded-lg border border-red-900/50 bg-red-950/30 text-red-300 space-y-3"
        >
          <div className="flex items-center gap-2 font-semibold text-red-200">
            <span className="w-2.5 h-2.5 rounded-full bg-red-500 inline-block" />
            Backend Connection Failed
          </div>
          <p className="text-sm font-mono bg-black/40 p-3 rounded border border-red-900/30">
            {error.message || "Failed to fetch /health. Verify that the backend server is running on port 8000."}
          </p>
          <button
            onClick={() => refetch()}
            className="px-3 py-1.5 text-xs font-medium bg-red-900/40 hover:bg-red-800/50 border border-red-700/50 rounded transition-colors"
          >
            Retry Connection
          </button>
        </div>
      )}

      {data && (
        <div
          id="health-success"
          className="p-6 rounded-lg border border-emerald-900/40 bg-emerald-950/20 text-emerald-300 space-y-4"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 font-semibold text-emerald-200">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 inline-block animate-pulse" />
              Backend Connected Successfully
            </div>
            <span className="text-xs font-mono uppercase bg-emerald-900/60 text-emerald-300 px-2 py-0.5 rounded border border-emerald-700/50">
              {data.status}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-4 text-xs font-mono pt-2 border-t border-emerald-900/30">
            <div>
              <span className="text-slate-400 block mb-1">Environment</span>
              <span className="text-slate-200 font-bold">{data.env}</span>
            </div>
            <div>
              <span className="text-slate-400 block mb-1">Status</span>
              <span className="text-emerald-400 font-bold">{data.status}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
