import { useState } from "react";
import { Link } from "react-router-dom";
import { useFileBlastMutation, useFileDeps, useRepoGraph } from "../../lib/repos";

interface MappingSidebarProps {
  repoId: number | string;
  activeFilePath?: string | null;
  onOpenFile?: (path: string) => void;
}

export function MappingSidebar({
  repoId,
  activeFilePath,
  onOpenFile,
}: MappingSidebarProps) {
  const { data: graph, isLoading } = useRepoGraph(repoId);
  const [selectedFile, setSelectedFile] = useState<string>(activeFilePath || "");
  const [searchFilter, setSearchFilter] = useState("");

  const { data: fileDeps } = useFileDeps(repoId, selectedFile || null, Boolean(selectedFile));
  const blastMutation = useFileBlastMutation(repoId);

  const handleComputeBlast = () => {
    if (selectedFile) {
      blastMutation.mutate({ file: selectedFile, includeTypeOnly: true });
    }
  };

  const allFiles = graph?.nodes.map((n) => n.id) || [];
  const filteredFiles = searchFilter
    ? allFiles.filter((f) => f.toLowerCase().includes(searchFilter.toLowerCase()))
    : allFiles.slice(0, 50);

  return (
    <div className="w-80 bg-neutral-900 border-r border-neutral-800 flex flex-col h-full text-xs text-neutral-300 overflow-hidden select-none">
      {/* Header */}
      <div className="px-4 py-3 border-b border-neutral-800 flex items-center justify-between bg-neutral-900/90 shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-orange-400 font-bold">🗺️</span>
          <span className="font-semibold uppercase tracking-wider text-[11px] text-neutral-200">
            GitHub Mapping
          </span>
        </div>
        <Link
          to={`/repos/${repoId}`}
          className="text-[10px] text-orange-400 hover:text-orange-300 font-medium px-2 py-0.5 rounded bg-orange-500/10 hover:bg-orange-500/20 transition-colors"
        >
          Open 2D Canvas &rarr;
        </Link>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-4">
        {/* AST Graph Stats */}
        <div className="p-3 rounded-xl bg-neutral-950/60 border border-neutral-800 space-y-2.5">
          <div className="text-[10px] font-bold uppercase tracking-wider text-neutral-400">
            Deterministic AST Topology
          </div>
          {isLoading ? (
            <div className="py-2 text-center text-neutral-500 animate-pulse">
              Parsing AST graph...
            </div>
          ) : graph ? (
            <div className="grid grid-cols-2 gap-2 text-neutral-300">
              <div className="p-2 rounded bg-neutral-900/80 border border-neutral-850">
                <span className="text-[10px] text-neutral-500 block">Source Nodes</span>
                <span className="font-mono font-bold text-orange-400 text-sm">
                  {graph.stats?.files ?? graph.nodes?.length ?? 0}
                </span>
              </div>
              <div className="p-2 rounded bg-neutral-900/80 border border-neutral-850">
                <span className="text-[10px] text-neutral-500 block">Import Edges</span>
                <span className="font-mono font-bold text-emerald-400 text-sm">
                  {graph.stats?.edges ?? graph.edges?.length ?? 0}
                </span>
              </div>
              <div className="p-2 rounded bg-neutral-900/80 border border-neutral-850">
                <span className="text-[10px] text-neutral-500 block">External Pkgs</span>
                <span className="font-mono font-bold text-sky-400 text-sm">
                  {graph.stats?.external_packages ?? 0}
                </span>
              </div>
              <div className="p-2 rounded bg-neutral-900/80 border border-neutral-850">
                <span className="text-[10px] text-neutral-500 block">Dependency Cycles</span>
                <span className="font-mono font-bold text-amber-400 text-sm">
                  {graph.stats?.cycles ?? 0}
                </span>
              </div>
            </div>
          ) : (
            <div className="text-neutral-500 text-[11px]">No graph parsed yet.</div>
          )}
        </div>

        {/* File Dependency & Blast Radius Inspector */}
        <div className="space-y-2">
          <div className="text-[10px] font-bold uppercase tracking-wider text-neutral-400">
            Blast Radius &amp; Dependency Walk
          </div>

          <div className="space-y-1.5">
            <input
              type="text"
              placeholder="Filter files to inspect..."
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              className="w-full px-2.5 py-1.5 rounded-lg bg-neutral-950 border border-neutral-800 text-neutral-200 placeholder-neutral-600 focus:outline-none focus:border-orange-500 font-mono text-[11px]"
            />

            {filteredFiles.length > 0 && !selectedFile && (
              <div className="max-h-28 overflow-y-auto rounded-lg border border-neutral-800 bg-neutral-950/80 divide-y divide-neutral-900 font-mono text-[11px]">
                {filteredFiles.slice(0, 10).map((file) => (
                  <button
                    key={file}
                    type="button"
                    onClick={() => {
                      setSelectedFile(file);
                      setSearchFilter("");
                    }}
                    className="w-full text-left px-2 py-1 hover:bg-neutral-800 text-neutral-300 truncate cursor-pointer"
                  >
                    {file}
                  </button>
                ))}
              </div>
            )}
          </div>

          {selectedFile && (
            <div className="p-3 rounded-xl bg-neutral-950 border border-neutral-800 space-y-3">
              <div className="flex items-center justify-between">
                <span className="font-mono text-orange-400 font-semibold truncate max-w-[200px]" title={selectedFile}>
                  {selectedFile.split("/").pop()}
                </span>
                <button
                  type="button"
                  onClick={() => setSelectedFile("")}
                  className="text-[10px] text-neutral-500 hover:text-neutral-300 cursor-pointer"
                >
                  Clear
                </button>
              </div>

              {onOpenFile && (
                <button
                  type="button"
                  onClick={() => onOpenFile(selectedFile)}
                  className="w-full py-1 px-2 rounded bg-neutral-800 hover:bg-neutral-700 text-[11px] text-neutral-200 font-medium transition-colors cursor-pointer"
                >
                  Open in Code Editor
                </button>
              )}

              {/* Direct Dependencies & Dependents */}
              {fileDeps && (
                <div className="space-y-2 pt-1 border-t border-neutral-850">
                  <div>
                    <span className="text-[10px] text-neutral-500 font-semibold uppercase block">
                      Imports ({fileDeps.dependencies.length})
                    </span>
                    <div className="max-h-20 overflow-y-auto space-y-0.5 mt-1 font-mono text-[10px] text-neutral-400">
                      {fileDeps.dependencies.length === 0 ? (
                        <span className="text-neutral-600">None</span>
                      ) : (
                        fileDeps.dependencies.map((dep) => (
                          <div key={dep} className="truncate" title={dep}>
                            &rarr; {dep}
                          </div>
                        ))
                      )}
                    </div>
                  </div>

                  <div>
                    <span className="text-[10px] text-neutral-500 font-semibold uppercase block">
                      Imported By ({fileDeps.dependents.length})
                    </span>
                    <div className="max-h-20 overflow-y-auto space-y-0.5 mt-1 font-mono text-[10px] text-neutral-400">
                      {fileDeps.dependents.length === 0 ? (
                        <span className="text-neutral-600">None</span>
                      ) : (
                        fileDeps.dependents.map((dep) => (
                          <div key={dep} className="truncate text-emerald-400/90" title={dep}>
                            &larr; {dep}
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* Compute Blast Radius button */}
              <button
                type="button"
                onClick={handleComputeBlast}
                disabled={blastMutation.isPending}
                className="w-full py-1.5 px-3 rounded-lg bg-orange-500 hover:bg-orange-600 text-white font-semibold text-[11px] transition-all flex items-center justify-center gap-1.5 cursor-pointer shadow-md shadow-orange-500/20 disabled:opacity-50"
              >
                {blastMutation.isPending ? (
                  <>
                    <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    <span>Calculating Blast...</span>
                  </>
                ) : (
                  <span>Calculate Blast Radius</span>
                )}
              </button>

              {blastMutation.data && (
                <div className="p-2.5 rounded-lg bg-orange-950/30 border border-orange-900/50 space-y-1">
                  <div className="flex items-center justify-between text-orange-300 font-semibold text-[11px]">
                    <span>Total Impacted Files:</span>
                    <span className="font-mono">{blastMutation.data.total}</span>
                  </div>
                  <div className="max-h-24 overflow-y-auto space-y-0.5 text-[10px] font-mono text-orange-200/80">
                    {blastMutation.data.impacts.map((imp) => (
                      <div key={imp.file} className="truncate">
                        depth {imp.depth}: {imp.file}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
