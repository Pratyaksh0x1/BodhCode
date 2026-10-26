import { useParams } from "react-router-dom";

export function RepoDetail() {
  const { id } = useParams<{ id: string }>();

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight text-slate-100">
        Repository Analysis: <span className="font-mono text-sky-400">{id}</span>
      </h1>
      <p className="text-sm text-slate-400">
        Interactive dependency map and editor shell (reserved for future phases).
      </p>
      <div className="p-8 rounded-lg border border-slate-800 bg-slate-900/30 text-center text-slate-500 font-mono text-sm">
        [Dependency Map & Blast Radius Visualizer Slot]
      </div>
    </div>
  );
}
