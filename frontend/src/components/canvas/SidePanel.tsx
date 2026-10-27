import { memo, useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import { useNavigate } from "react-router-dom";
import { useReactFlow } from "@xyflow/react";
import { useGraphStore } from "../../store/graphStore";
import {
  useExplainFile,
  useFileBlastMutation,
  useFileDeps,
  type ExplainResponse,
} from "../../lib/repos";
import { useMe } from "../../lib/auth";
import { useLanguages } from "../../lib/settings";
import { useGraphContext } from "./GraphContext";

interface SidePanelProps {
  repoId: number | string;
}

export const SidePanel = memo(function SidePanel({ repoId }: SidePanelProps) {
  const navigate = useNavigate();
  const graph = useGraphContext();
  const selectedFileId = useGraphStore((s) => s.selectedFileId);
  const select = useGraphStore((s) => s.select);
  const expandPathTo = useGraphStore((s) => s.expandPathTo);
  const blast = useGraphStore((s) => s.blast);
  const setBlast = useGraphStore((s) => s.setBlast);
  const clearBlast = useGraphStore((s) => s.clearBlast);
  const { fitView } = useReactFlow();

  const [width, setWidth] = useState(380);
  const [isResizing, setIsResizing] = useState(false);

  // Fetch API deps
  const { data: depsData, isLoading: isDepsLoading } = useFileDeps(
    repoId,
    selectedFileId,
    Boolean(selectedFileId)
  );

  // Blast mutation
  const blastMutation = useFileBlastMutation(repoId);

  // Find the selected file node
  const selectedNode = useMemo(() => {
    if (!selectedFileId) return null;
    return graph.nodes.find((n) => n.id === selectedFileId) || null;
  }, [graph.nodes, selectedFileId]);

  // Fallback to graph.edges if deps endpoint is loading or for immediate rendering
  const directDependents = useMemo(() => {
    if (!selectedFileId) return [];
    if (depsData?.dependents) {
      return depsData.dependents;
    }
    const set = new Set<string>();
    for (const e of graph.edges) {
      if (e.target === selectedFileId) {
        set.add(e.source);
      }
    }
    return Array.from(set).sort();
  }, [depsData?.dependents, graph.edges, selectedFileId]);

  const directDependencies = useMemo(() => {
    if (!selectedFileId) return [];
    if (depsData?.dependencies) {
      return depsData.dependencies;
    }
    const set = new Set<string>();
    for (const e of graph.edges) {
      if (e.source === selectedFileId) {
        set.add(e.target);
      }
    }
    return Array.from(set).sort();
  }, [depsData?.dependencies, graph.edges, selectedFileId]);

  // Navigate to another file on click
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

  const handleShowBlast = async () => {
    if (!selectedFileId) return;
    try {
      const res = await blastMutation.mutateAsync({ file: selectedFileId });
      setBlast(res);
    } catch (err) {
      console.error("Failed to fetch blast radius:", err);
    }
  };

  // Group blast impacts by depth
  const impactsByDepth = useMemo(() => {
    if (!blast || !selectedFileId || blast.file !== selectedFileId) {
      return new Map<number, string[]>();
    }
    const map = new Map<number, string[]>();
    for (const imp of blast.impacts) {
      const list = map.get(imp.depth) || [];
      list.push(imp.file);
      map.set(imp.depth, list);
    }
    return map;
  }, [blast, selectedFileId]);

  // User language & Explain mutation
  const { data: user } = useMe();
  const { data: languages } = useLanguages();
  const currentLanguageCode = user?.preferred_language || "en";
  const currentLanguage = useMemo(() => {
    return languages?.find((l) => l.code === currentLanguageCode) || null;
  }, [languages, currentLanguageCode]);
  const languageLabel =
    currentLanguage?.native_name || currentLanguage?.english_name || currentLanguageCode;

  const explainMutation = useExplainFile(repoId);
  const [explanationResult, setExplanationResult] = useState<ExplainResponse | null>(null);

  // Clear explanation when changing selected files
  useEffect(() => {
    setExplanationResult(null);
  }, [selectedFileId]);

  const handleExplain = async (refresh: boolean = false) => {
    if (!selectedFileId) return;
    try {
      const res = await explainMutation.mutateAsync({
        filePath: selectedFileId,
        language: currentLanguageCode,
        refresh,
      });
      setExplanationResult(res);
    } catch (err) {
      console.error("Failed to explain file:", err);
    }
  };

  // Handle panel resizing
  const startResizing = (mouseDownEvent: React.MouseEvent) => {
    mouseDownEvent.preventDefault();
    setIsResizing(true);

    const startX = mouseDownEvent.clientX;
    const startWidth = width;

    function onMouseMove(moveEvent: MouseEvent) {
      const delta = startX - moveEvent.clientX;
      const newWidth = Math.min(Math.max(startWidth + delta, 300), 650);
      setWidth(newWidth);
    }

    function onMouseUp() {
      setIsResizing(false);
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    }

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    return `${(bytes / 1024).toFixed(1)} KB`;
  };

  if (!selectedFileId || !selectedNode) {
    return null;
  }

  return (
    <aside
      id="canvas-side-panel"
      aria-label="File Details Side Panel"
      style={{ width }}
      className={`relative h-full bg-white/95 dark:bg-neutral-900/95 backdrop-blur-md border-l border-neutral-200 dark:border-neutral-800 shadow-2xl flex flex-col z-30 select-none text-neutral-800 dark:text-neutral-100 transition-colors ${
        isResizing ? "cursor-ew-resize" : ""
      }`}
    >
      {/* Resizing handle on the left edge */}
      <div
        onMouseDown={startResizing}
        aria-label="Resize panel width"
        className="absolute -left-1 top-0 bottom-0 w-2 cursor-ew-resize hover:bg-orange-500/50 transition-colors z-40"
      />

      {/* Header */}
      <div className="p-4 border-b border-neutral-200 dark:border-neutral-800 flex items-start justify-between gap-2">
        <div className="overflow-hidden">
          <span className="text-[10px] font-mono uppercase tracking-wider text-neutral-400 dark:text-neutral-500 block">
            Selected File
          </span>
          <h3
            className="text-sm font-bold text-neutral-900 dark:text-neutral-100 truncate"
            title={selectedNode.id}
          >
            {selectedNode.name}
          </h3>
          <p className="text-xs font-mono text-neutral-500 dark:text-neutral-400 truncate">
            {selectedNode.folder || "."}
          </p>
        </div>

        <button
          type="button"
          aria-label="Close details panel"
          onClick={() => select(null)}
          className="p-1 rounded-lg text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors cursor-pointer"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Content scroll area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-5 text-xs">
        {/* File properties */}
        <div className="grid grid-cols-2 gap-2 text-neutral-600 dark:text-neutral-400 font-mono">
          <div className="p-2 rounded-lg bg-neutral-100 dark:bg-neutral-800/60 border border-neutral-200 dark:border-neutral-800">
            <span className="text-[10px] block opacity-70">Size</span>
            <span className="font-semibold text-neutral-900 dark:text-neutral-100">
              {formatSize(selectedNode.size)}
            </span>
          </div>

          <div className="p-2 rounded-lg bg-neutral-100 dark:bg-neutral-800/60 border border-neutral-200 dark:border-neutral-800">
            <span className="text-[10px] block opacity-70">Exports</span>
            <span className="font-semibold text-neutral-900 dark:text-neutral-100">
              {selectedNode.exports.length}
            </span>
          </div>
        </div>

        {/* Blast Radius Section */}
        <div className="p-3 rounded-xl bg-orange-50/60 dark:bg-orange-950/20 border border-orange-200 dark:border-orange-800/60 space-y-2.5">
          <div className="flex items-center justify-between">
            <span className="font-bold text-orange-900 dark:text-orange-200">
              Blast Radius
            </span>
            {blast && blast.file === selectedFileId && (
              <span className="text-[11px] font-mono font-bold px-2 py-0.5 rounded-full bg-orange-500/20 text-orange-600 dark:text-orange-300 border border-orange-500/40">
                {blast.total} impacted
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              id="show-blast-radius-btn"
              onClick={handleShowBlast}
              disabled={blastMutation.isPending}
              className="flex-1 px-3 py-1.5 rounded-lg text-xs font-semibold bg-orange-500 hover:bg-orange-600 text-white transition-all shadow-sm cursor-pointer disabled:opacity-60 flex items-center justify-center gap-1.5"
            >
              {blastMutation.isPending ? (
                <>
                  <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  <span>Computing...</span>
                </>
              ) : (
                <>
                  <span>Show blast radius</span>
                </>
              )}
            </button>

            {blast && (
              <button
                type="button"
                id="clear-blast-radius-btn"
                onClick={clearBlast}
                className="px-3 py-1.5 rounded-lg text-xs font-medium border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-700 transition-colors cursor-pointer"
              >
                Clear
              </button>
            )}
          </div>

          {/* Depth grouped list if blast is active for this file */}
          {blast && blast.file === selectedFileId && (
            <div className="pt-2 border-t border-orange-200 dark:border-orange-900/50 space-y-2 max-h-48 overflow-y-auto">
              {Array.from(impactsByDepth.entries())
                .sort(([d1], [d2]) => d1 - d2)
                .map(([depth, files]) => (
                  <div key={depth} className="space-y-1">
                    <span className="text-[10px] font-mono font-bold text-neutral-500 uppercase">
                      Depth {depth} ({files.length} {files.length === 1 ? "file" : "files"})
                    </span>
                    <ul className="space-y-0.5">
                      {files.map((f) => (
                        <li key={f}>
                          <button
                            type="button"
                            onClick={() => handleNavigate(f)}
                            className="w-full text-left font-mono text-[11px] px-2 py-0.5 rounded hover:bg-orange-200/50 dark:hover:bg-orange-900/30 text-orange-950 dark:text-orange-200 truncate block transition-colors cursor-pointer"
                          >
                            &bull; {f}
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
            </div>
          )}
        </div>

        {/* Grounded File Explanation Section */}
        <div className="p-3 rounded-xl bg-sky-50/60 dark:bg-sky-950/20 border border-sky-200 dark:border-sky-800/60 space-y-2.5">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5 overflow-hidden">
              <span className="font-bold text-sky-900 dark:text-sky-200">
                Grounded Explanation
              </span>
              <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-sky-100 dark:bg-sky-900/60 text-sky-700 dark:text-sky-300 border border-sky-200 dark:border-sky-800">
                {languageLabel}
              </span>
            </div>

            {explanationResult && (
              <div className="flex items-center gap-1.5">
                {explanationResult.cached && (
                  <span
                    className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800"
                    title="Served from deterministic cache"
                  >
                    ⚡ Cached
                  </span>
                )}
                {import.meta.env.DEV && (
                  <button
                    type="button"
                    onClick={() => handleExplain(true)}
                    disabled={explainMutation.isPending}
                    className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-neutral-200 dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300 hover:bg-neutral-300 dark:hover:bg-neutral-700 transition-colors cursor-pointer disabled:opacity-50"
                    title="Regenerate explanation (bypasses cache in DEV mode)"
                  >
                    Regenerate
                  </button>
                )}
              </div>
            )}
          </div>

          {!explanationResult && !explainMutation.isPending && (
            <button
              type="button"
              id="explain-file-btn"
              onClick={() => handleExplain(false)}
              className="w-full px-3 py-1.5 rounded-lg text-xs font-semibold bg-sky-600 hover:bg-sky-700 text-white transition-all shadow-sm cursor-pointer flex items-center justify-center gap-1.5"
            >
              <span>✨ Explain {selectedNode.name}</span>
            </button>
          )}

          {explainMutation.isPending && (
            <div className="py-3 px-2 flex flex-col items-center justify-center gap-2 text-sky-700 dark:text-sky-300 bg-sky-100/50 dark:bg-sky-900/20 rounded-lg">
              <div className="w-4 h-4 border-2 border-sky-600 border-t-transparent rounded-full animate-spin" />
              <p className="text-[11px] font-medium text-center">
                Explaining {selectedNode.name} in {languageLabel}...
              </p>
            </div>
          )}

          {explainMutation.isError && (
            <div className="p-2 rounded bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 text-rose-700 dark:text-rose-300 text-[11px] space-y-1">
              <span className="font-semibold block">Failed to explain file</span>
              <p className="opacity-90">{explainMutation.error?.message || "An unexpected error occurred."}</p>
              <button
                type="button"
                onClick={() => handleExplain(false)}
                className="mt-1 px-2 py-0.5 rounded text-[10px] bg-rose-100 dark:bg-rose-900 hover:bg-rose-200 text-rose-800 dark:text-rose-200 font-medium cursor-pointer"
              >
                Try again
              </button>
            </div>
          )}

          {explanationResult && (
            <div className="space-y-2">
              <div className="prose prose-sm dark:prose-invert max-w-none text-neutral-800 dark:text-neutral-200 text-xs leading-relaxed max-h-72 overflow-y-auto p-2.5 rounded-lg bg-white/70 dark:bg-neutral-900/70 border border-sky-100 dark:border-sky-950">
                <ReactMarkdown
                  components={{
                    code: ({ children, ...props }) => {
                      const text = String(children).trim();
                      const isVerified = explanationResult.verified_files.includes(text);
                      const isFlagged =
                        text.includes("⚠unverified") ||
                        explanationResult.flagged.includes(text.replace(" ⚠unverified", ""));

                      if (isVerified) {
                        return (
                          <button
                            type="button"
                            onClick={() => handleNavigate(text)}
                            className="inline-flex items-center font-mono text-[11px] px-1 py-0.2 rounded bg-sky-100 dark:bg-sky-900/70 text-sky-800 dark:text-sky-200 hover:underline cursor-pointer border border-sky-300 dark:border-sky-700 transition-colors"
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
                            <span className="font-bold text-amber-600 dark:text-amber-400">⚠</span>
                          </span>
                        );
                      }

                      return (
                        <code
                          className="bg-neutral-100 dark:bg-neutral-800 px-1 py-0.5 rounded font-mono text-[11px]"
                          {...props}
                        >
                          {children}
                        </code>
                      );
                    },
                  }}
                >
                  {explanationResult.explanation}
                </ReactMarkdown>
              </div>

              {/* Verified file chips */}
              {explanationResult.verified_files.length > 0 && (
                <div className="pt-2 border-t border-sky-200/50 dark:border-sky-900/40 space-y-1">
                  <span className="text-[10px] font-mono uppercase tracking-wider text-neutral-400 dark:text-neutral-500 block">
                    Verified Mentions ({explanationResult.verified_files.length})
                  </span>
                  <div className="flex flex-wrap gap-1">
                    {explanationResult.verified_files.map((file) => (
                      <button
                        key={file}
                        type="button"
                        onClick={() => handleNavigate(file)}
                        className="text-[11px] font-mono px-2 py-0.5 rounded bg-sky-100/70 dark:bg-sky-900/50 text-sky-700 dark:text-sky-300 hover:bg-sky-200 dark:hover:bg-sky-800 border border-sky-300/60 dark:border-sky-800 transition-colors cursor-pointer truncate max-w-full"
                        title={`Navigate to ${file}`}
                      >
                        {file}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Flagged unverified mentions */}
              {explanationResult.flagged.length > 0 && (
                <div className="pt-1 flex flex-wrap gap-1">
                  {explanationResult.flagged.map((file) => (
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
            </div>
          )}
        </div>

        {/* Flags & Diagnostic Warnings */}
        {(selectedNode.flags.length > 0 || selectedNode.unresolved_count > 0) && (
          <div className="space-y-1.5 p-3 rounded-xl bg-amber-50/60 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800/60">
            <span className="font-semibold text-amber-900 dark:text-amber-200 block text-[11px]">
              Diagnostics &amp; Flags
            </span>
            <div className="flex flex-wrap gap-1.5">
              {selectedNode.flags.includes("in_cycle") && (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/20 text-amber-700 dark:text-amber-300 border border-amber-500/40">
                  ⚠️ Circular Dependency Loop
                </span>
              )}
              {selectedNode.flags.includes("parse_error") && (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/20 text-rose-700 dark:text-rose-300 border border-rose-500/40">
                  ⛔ Tree-Sitter Parse Error
                </span>
              )}
              {selectedNode.unresolved_count > 0 && (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-neutral-200 dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300">
                  {selectedNode.unresolved_count} unresolved imports
                </span>
              )}
            </div>
          </div>
        )}

        {/* Imported By (Dependents) */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="font-bold text-neutral-700 dark:text-neutral-300">
              Imported by ({directDependents.length})
            </span>
            {isDepsLoading && (
              <span className="text-[10px] text-neutral-400">Loading...</span>
            )}
          </div>
          {directDependents.length === 0 ? (
            <p className="text-[11px] text-neutral-400 italic">No files import this module directly.</p>
          ) : (
            <div className="max-h-36 overflow-y-auto space-y-1 p-1 bg-neutral-50 dark:bg-neutral-800/40 rounded-lg border border-neutral-200 dark:border-neutral-800">
              {directDependents.map((dep) => (
                <button
                  key={dep}
                  type="button"
                  onClick={() => handleNavigate(dep)}
                  className="w-full text-left font-mono text-[11px] px-2 py-1 rounded hover:bg-neutral-200 dark:hover:bg-neutral-700/60 text-sky-700 dark:text-sky-400 truncate block transition-colors cursor-pointer"
                  title={`Navigate to ${dep}`}
                >
                  &larr; {dep}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Imports (Dependencies) */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="font-bold text-neutral-700 dark:text-neutral-300">
              Imports ({directDependencies.length})
            </span>
            {isDepsLoading && (
              <span className="text-[10px] text-neutral-400">Loading...</span>
            )}
          </div>
          {directDependencies.length === 0 ? (
            <p className="text-[11px] text-neutral-400 italic">This file imports no local repository files.</p>
          ) : (
            <div className="max-h-36 overflow-y-auto space-y-1 p-1 bg-neutral-50 dark:bg-neutral-800/40 rounded-lg border border-neutral-200 dark:border-neutral-800">
              {directDependencies.map((dep) => (
                <button
                  key={dep}
                  type="button"
                  onClick={() => handleNavigate(dep)}
                  className="w-full text-left font-mono text-[11px] px-2 py-1 rounded hover:bg-neutral-200 dark:hover:bg-neutral-700/60 text-violet-700 dark:text-violet-400 truncate block transition-colors cursor-pointer"
                  title={`Navigate to ${dep}`}
                >
                  &rarr; {dep}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* External Packages */}
        <div className="space-y-1.5">
          <span className="font-bold text-neutral-700 dark:text-neutral-300 block">
            External Packages ({selectedNode.external_deps.length})
          </span>
          {selectedNode.external_deps.length === 0 ? (
            <p className="text-[11px] text-neutral-400 italic">No external packages imported.</p>
          ) : (
            <div className="flex flex-wrap gap-1">
              {selectedNode.external_deps.map((pkg) => (
                <span
                  key={pkg}
                  className="px-2 py-0.5 rounded-md font-mono text-[10px] bg-neutral-100 dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300 border border-neutral-200 dark:border-neutral-700"
                >
                  {pkg}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Exports List */}
        <div className="space-y-1.5">
          <span className="font-bold text-neutral-700 dark:text-neutral-300 block">
            Declared Exports ({selectedNode.exports.length})
          </span>
          {selectedNode.exports.length === 0 ? (
            <p className="text-[11px] text-neutral-400 italic">No named or default exports.</p>
          ) : (
            <div className="flex flex-wrap gap-1 max-h-28 overflow-y-auto">
              {selectedNode.has_default_export && (
                <span className="px-2 py-0.5 rounded-md font-mono text-[10px] bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 font-semibold">
                  default
                </span>
              )}
              {selectedNode.exports.map((exp) => (
                <span
                  key={exp}
                  className="px-2 py-0.5 rounded-md font-mono text-[10px] bg-neutral-100 dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300 border border-neutral-200 dark:border-neutral-700"
                >
                  {exp}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Open in editor (Phase 11) */}
        <div className="pt-2 border-t border-neutral-200 dark:border-neutral-800">
          <button
            type="button"
            onClick={() => {
              if (selectedNode) {
                navigate(`/repos/${repoId}/editor?file=${encodeURIComponent(selectedNode.id)}`);
              }
            }}
            title="Open in editor"
            className="w-full py-2 px-3 rounded-lg text-xs font-semibold bg-orange-600 hover:bg-orange-500 text-white border border-orange-500 flex items-center justify-center gap-2 transition-colors cursor-pointer shadow-sm"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"
              />
            </svg>
            <span>Open in editor</span>
          </button>
        </div>
      </div>
    </aside>
  );
});
