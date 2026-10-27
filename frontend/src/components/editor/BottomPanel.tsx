import { useState } from "react";
import { DiffEditor } from "@monaco-editor/react";
import type { ChangedFileItem, FileDiffResponse } from "../../lib/files";
import type { ResolvedEditorTheme } from "../../lib/theme";

interface BottomPanelProps {
  changes: ChangedFileItem[];
  activeDiffPath: string | null;
  diffData: FileDiffResponse | null;
  isDiffLoading: boolean;
  onSelectDiffFile: (path: string) => void;
  onRevertFile: (path: string) => void;
  onClosePanel: () => void;
  onOpenPushModal?: () => void;
  theme: ResolvedEditorTheme;
}

export function BottomPanel({
  changes,
  activeDiffPath,
  diffData,
  isDiffLoading,
  onSelectDiffFile,
  onRevertFile,
  onClosePanel,
  onOpenPushModal,
  theme,
}: BottomPanelProps) {
  const [activeTab, setActiveTab] = useState<"changes" | "problems">("changes");
  const [isSideBySide, setIsSideBySide] = useState(true);

  return (
    <div className="h-full flex flex-col bg-neutral-950 border-t border-neutral-800 text-neutral-200 overflow-hidden">
      {/* Panel Header */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-neutral-900 border-b border-neutral-800 text-xs shrink-0 select-none">
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setActiveTab("changes")}
            className={`px-3 py-1 rounded font-medium flex items-center gap-1.5 transition-colors cursor-pointer ${
              activeTab === "changes"
                ? "bg-neutral-800 text-orange-400"
                : "text-neutral-400 hover:text-neutral-200"
            }`}
          >
            <span>Changes</span>
            <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-neutral-700/60 font-mono">
              {changes.length}
            </span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("problems")}
            className={`px-3 py-1 rounded font-medium flex items-center gap-1.5 transition-colors cursor-pointer ${
              activeTab === "problems"
                ? "bg-neutral-800 text-orange-400"
                : "text-neutral-400 hover:text-neutral-200"
            }`}
          >
            <span>Problems</span>
            <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-neutral-700/60 font-mono">
              0
            </span>
          </button>
        </div>

        {/* Right side controls */}
        <div className="flex items-center gap-2">
          {activeTab === "changes" && changes.length > 0 && onOpenPushModal && (
            <button
              type="button"
              onClick={onOpenPushModal}
              className="px-2.5 py-0.5 rounded bg-orange-500 hover:bg-orange-600 text-white font-semibold text-[11px] flex items-center gap-1.5 transition-colors shadow-sm shadow-orange-500/20 cursor-pointer"
            >
              <span>🚀</span>
              <span>Push Changes</span>
            </button>
          )}

          {activeTab === "changes" && activeDiffPath && (
            <button
              type="button"
              onClick={() => setIsSideBySide(!isSideBySide)}
              title={isSideBySide ? "Switch to inline diff view" : "Switch to side-by-side diff view"}
              className="px-2 py-0.5 rounded bg-neutral-800 hover:bg-neutral-700 text-[11px] text-neutral-300 transition-colors"
            >
              {isSideBySide ? "Inline Diff" : "Side-by-side"}
            </button>
          )}

          <button
            type="button"
            onClick={onClosePanel}
            title="Close Panel (Ctrl+J)"
            className="p-1 rounded text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800 cursor-pointer"
          >
            ✕
          </button>
        </div>
      </div>

      {/* Panel Content */}
      <div className="flex-1 overflow-hidden">
        {activeTab === "problems" && (
          <div className="h-full flex items-center justify-center text-xs text-neutral-500">
            Diagnostics not available yet
          </div>
        )}

        {activeTab === "changes" && (
          <div className="h-full flex">
            {/* File List Pane */}
            <div className="w-64 border-r border-neutral-800 overflow-y-auto shrink-0 bg-neutral-900/30">
              {changes.length === 0 ? (
                <div className="p-4 text-xs text-neutral-500 text-center">
                  No changes in working copy.
                </div>
              ) : (
                <div className="divide-y divide-neutral-900">
                  {changes.map((item) => {
                    const isSelected = item.path === activeDiffPath;
                    return (
                      <div
                        key={item.path}
                        onClick={() => onSelectDiffFile(item.path)}
                        className={`flex items-center justify-between px-3 py-2 text-xs cursor-pointer group transition-colors ${
                          isSelected
                            ? "bg-orange-500/15 text-orange-300 font-medium"
                            : "text-neutral-300 hover:bg-neutral-800/40"
                        }`}
                      >
                        <div className="flex items-center gap-2 overflow-hidden">
                          <span
                            className={`text-[10px] font-bold ${
                              item.status === "modified"
                                ? "text-amber-400"
                                : item.status === "added"
                                ? "text-emerald-400"
                                : "text-rose-400 line-through"
                            }`}
                          >
                            {item.status === "modified" ? "M" : item.status === "added" ? "A" : "D"}
                          </span>
                          <span className="truncate">{item.path}</span>
                        </div>

                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onRevertFile(item.path);
                          }}
                          title="Revert file"
                          className="opacity-0 group-hover:opacity-100 text-[10px] px-1.5 py-0.5 rounded bg-neutral-800 hover:bg-neutral-700 text-amber-400 shrink-0"
                        >
                          Revert
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Diff Viewer Pane */}
            <div className="flex-1 h-full overflow-hidden bg-neutral-950">
              {!activeDiffPath ? (
                <div className="h-full flex items-center justify-center text-xs text-neutral-500">
                  Select a changed file to view diff
                </div>
              ) : isDiffLoading ? (
                <div className="h-full flex items-center justify-center text-xs text-neutral-400 gap-2">
                  <div className="w-4 h-4 border-2 border-orange-400 border-t-transparent rounded-full animate-spin" />
                  <span>Loading diff...</span>
                </div>
              ) : diffData ? (
                <div className="h-full w-full">
                  <DiffEditor
                    key={`${activeDiffPath}-${isSideBySide}`}
                    original={diffData.original}
                    modified={diffData.modified}
                    theme={theme}
                    options={{
                      renderSideBySide: isSideBySide,
                      readOnly: true,
                      automaticLayout: true,
                      minimap: { enabled: false },
                      fontSize: 12,
                    }}
                  />
                </div>
              ) : (
                <div className="h-full flex items-center justify-center text-xs text-rose-400">
                  Failed to load diff
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
