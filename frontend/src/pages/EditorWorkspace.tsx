import { useEffect, useReducer, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Group, Panel, Separator } from "react-resizable-panels";
import { useMe } from "../lib/auth";
import {
  useDeleteFile,
  useFileContent,
  useFileDiff,
  useRenameFile,
  useRepoChanges,
  useRepoFiles,
  useRevertFile,
  useSaveFile,
} from "../lib/files";
import { useRepo } from "../lib/repos";
import {
  type EditorThemePref,
  resolveEditorTheme,
  useThemeStore,
} from "../lib/theme";
import { useQueryClient } from "@tanstack/react-query";
import { ActivityBar, type SidebarView } from "../components/editor/ActivityBar";
import { AgentPanel, type PendingSelection } from "../components/editor/agent/AgentPanel";
import { BottomPanel } from "../components/editor/BottomPanel";
import { EditorTabs } from "../components/editor/EditorTabs";
import { FileExplorer } from "../components/editor/FileExplorer";
import { MonacoEditorPane } from "../components/editor/MonacoEditorPane";
import { QuickOpenModal } from "../components/editor/QuickOpenModal";
import { StatusBar } from "../components/editor/StatusBar";
import { PushModalWizard } from "../components/editor/push/PushModalWizard";
import { initialTabState, tabReducer } from "../components/editor/tabState";

export function EditorWorkspace() {
  const { id } = useParams<{ id: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedFile = searchParams.get("file");

  const { data: user } = useMe();
  const { data: repo, isLoading: isRepoLoading, isError: isRepoError } = useRepo(id);
  const {
    data: filesData,
    isLoading: isFilesLoading,
    isError: isFilesError,
  } = useRepoFiles(id);
  const { data: changesData } = useRepoChanges(id);

  const saveMutation = useSaveFile(id);
  const deleteMutation = useDeleteFile(id);
  const revertMutation = useRevertFile(id);
  const renameMutation = useRenameFile(id);

  // Tab State
  const [tabState, dispatch] = useReducer(tabReducer, initialTabState);
  const activeTab = tabState.tabs.find((t) => t.path === tabState.activePath) || null;

  // Active file query for loading content
  const { data: activeContentData, error: activeContentError } = useFileContent(
    id,
    tabState.activePath
  );

  // Bottom diff query
  const [diffPath, setDiffPath] = useState<string | null>(null);
  const { data: diffData, isLoading: isDiffLoading } = useFileDiff(id, diffPath);

  // Layout UI states
  const [sidebarView, setSidebarView] = useState<SidebarView | null>("explorer");
  const [isBottomOpen, setIsBottomOpen] = useState(false);
  const [isAiOpen, setIsAiOpen] = useState(false);
  const [isQuickOpen, setIsQuickOpen] = useState(false);
  const [isPushModalOpen, setIsPushModalOpen] = useState(false);
  const [pendingSelection, setPendingSelection] = useState<PendingSelection | null>(null);
  const queryClient = useQueryClient();

  // Editor cursor & save status
  const [cursorPos, setCursorPos] = useState({ line: 1, col: 1 });
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [saveErrorMessage, setSaveErrorMessage] = useState<string | null>(null);

  // Theme resolution
  const appTheme = useThemeStore((s) => s.resolved);
  const editorTheme = resolveEditorTheme(
    (user?.editor_theme as EditorThemePref) || "auto",
    appTheme
  );

  // Load layout from localStorage
  const savedHorizontalLayout = (() => {
    try {
      const stored = localStorage.getItem("bodhcode.editor.layout.horizontal");
      return stored ? JSON.parse(stored) : undefined;
    } catch {
      return undefined;
    }
  })();

  const savedVerticalLayout = (() => {
    try {
      const stored = localStorage.getItem("bodhcode.editor.layout.vertical");
      return stored ? JSON.parse(stored) : undefined;
    } catch {
      return undefined;
    }
  })();

  // Handle URL file query on mount or change
  useEffect(() => {
    if (requestedFile) {
      dispatch({
        type: "OPEN_TAB",
        payload: { path: requestedFile },
      });
    }
  }, [requestedFile]);

  // When activeContentData loads, populate tab if not already modified
  useEffect(() => {
    if (activeContentData && tabState.activePath === activeContentData.path) {
      dispatch({
        type: "SET_LOADED_CONTENT",
        payload: {
          path: activeContentData.path,
          content: activeContentData.content,
          hash: activeContentData.content_hash || activeContentData.hash,
          baseHash: activeContentData.base_hash,
        },
      });
    }
  }, [activeContentData, tabState.activePath]);

  // Warn before leaving page with unsaved dirty files
  useEffect(() => {
    const hasDirty = tabState.tabs.some((t) => t.dirty);
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (hasDirty) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [tabState.tabs]);

  // Save active file
  const handleSave = async () => {
    if (!activeTab || !id) return;
    setSaveStatus("saving");
    setSaveErrorMessage(null);

    try {
      const result = await saveMutation.mutateAsync({
        path: activeTab.path,
        content: activeTab.content,
        ifMatch: activeTab.contentHash || activeTab.baseHash,
      });

      dispatch({
        type: "MARK_SAVED",
        payload: {
          path: activeTab.path,
          contentHash: result.content_hash || result.hash,
        },
      });

      setSaveStatus("saved");
      setTimeout(() => setSaveStatus("idle"), 2500);
    } catch (err: unknown) {
      setSaveStatus("error");
      const msg = err instanceof Error ? err.message : "Failed to save file";
      setSaveErrorMessage(msg);
      setTimeout(() => setSaveErrorMessage(null), 6000);
    }
  };

  // Global Keyboard Shortcuts (Ctrl+S, Ctrl+P, Ctrl+B, Ctrl+J)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const isCmdOrCtrl = e.metaKey || e.ctrlKey;
      if (isCmdOrCtrl && e.key.toLowerCase() === "p") {
        e.preventDefault();
        setIsQuickOpen((prev) => !prev);
      } else if (isCmdOrCtrl && e.key.toLowerCase() === "b") {
        e.preventDefault();
        setSidebarView((prev) => (prev ? null : "explorer"));
      } else if (isCmdOrCtrl && e.key.toLowerCase() === "j") {
        e.preventDefault();
        setIsBottomOpen((prev) => !prev);
      } else if (isCmdOrCtrl && e.key.toLowerCase() === "s") {
        e.preventDefault();
        handleSave();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  });

  // Open a file into tabs
  const handleOpenFile = (path: string) => {
    dispatch({ type: "OPEN_TAB", payload: { path } });
    setSearchParams({ file: path });
  };

  // Close tab with unsaved confirmation guard
  const handleCloseTab = (path: string) => {
    const tab = tabState.tabs.find((t) => t.path === path);
    if (tab?.dirty) {
      const confirmed = window.confirm(
        `"${tab.title}" has unsaved changes. Do you want to close it and discard your changes?`
      );
      if (!confirmed) return;
    }
    dispatch({ type: "CLOSE_TAB", payload: { path } });
  };

  // Close others with dirty check
  const handleCloseOthers = (path: string) => {
    const dirtyOthers = tabState.tabs.filter((t) => t.path !== path && t.dirty);
    if (dirtyOthers.length > 0) {
      const confirmed = window.confirm(
        `You have ${dirtyOthers.length} other tab(s) with unsaved changes. Close them and discard changes?`
      );
      if (!confirmed) return;
    }
    dispatch({ type: "CLOSE_OTHERS", payload: { path } });
  };

  // Create new file
  const handleCreateFile = async (newPath: string) => {
    try {
      await saveMutation.mutateAsync({
        path: newPath,
        content: "",
      });
      handleOpenFile(newPath);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to create file");
    }
  };

  // Rename file
  const handleRenameFile = async (oldPath: string, newPath: string) => {
    try {
      await renameMutation.mutateAsync({ oldPath, newPath });
      dispatch({ type: "CLOSE_TAB", payload: { path: oldPath } });
      handleOpenFile(newPath);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to rename file");
    }
  };

  // Delete file
  const handleDeleteFile = async (path: string) => {
    const confirmed = window.confirm(`Are you sure you want to delete "${path}" from your working copy?`);
    if (!confirmed) return;
    try {
      await deleteMutation.mutateAsync(path);
      dispatch({ type: "CLOSE_TAB", payload: { path } });
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to delete file");
    }
  };

  // Revert file
  const handleRevertFile = async (path: string) => {
    const confirmed = window.confirm(
      `Revert all working copy changes to "${path}" and restore original repository content?`
    );
    if (!confirmed) return;
    try {
      await revertMutation.mutateAsync(path);
      // Reload tab if currently open
      dispatch({ type: "CLOSE_TAB", payload: { path } });
      handleOpenFile(path);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to revert file");
    }
  };

  // Diff inspection
  const handleOpenDiff = (path: string) => {
    setDiffPath(path);
    setIsBottomOpen(true);
  };

  // Loading and Error states
  if (isRepoLoading || isFilesLoading) {
    return (
      <div className="h-screen w-full flex flex-col items-center justify-center bg-neutral-950 text-neutral-400 gap-3">
        <div className="w-8 h-8 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-sm">Loading code editor workspace...</p>
      </div>
    );
  }

  if (isRepoError || !repo) {
    return (
      <div className="h-screen w-full flex flex-col items-center justify-center bg-neutral-950 p-6 text-center space-y-4">
        <h2 className="text-lg font-semibold text-rose-300">Repository Not Found</h2>
        <p className="text-sm text-neutral-400">Unable to load the requested repository.</p>
        <Link
          to="/"
          className="px-4 py-2 rounded-lg bg-neutral-800 text-neutral-200 hover:bg-neutral-700 text-xs font-semibold"
        >
          &larr; Back to Dashboard
        </Link>
      </div>
    );
  }

  if (isFilesError) {
    return (
      <div className="h-screen w-full flex flex-col items-center justify-center bg-neutral-950 p-6 text-center space-y-4">
        <h2 className="text-lg font-semibold text-amber-300">Repository Files Unavailable</h2>
        <p className="text-sm text-neutral-400 max-w-md">
          The extracted files for this repository commit are unavailable or require re-ingestion at INGEST_VERSION 2.
        </p>
        <div className="flex gap-3">
          <Link
            to={`/repos/${repo.id}`}
            className="px-4 py-2 rounded-lg bg-orange-600 hover:bg-orange-500 text-white text-xs font-semibold"
          >
            Refresh / Ingest Repo
          </Link>
          <Link
            to="/"
            className="px-4 py-2 rounded-lg bg-neutral-800 text-neutral-200 hover:bg-neutral-700 text-xs font-semibold"
          >
            Back to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  const files = filesData?.files || [];
  const changes = changesData?.changes || [];
  const repoIdentifier = `${repo.owner}/${repo.name}@${repo.commit_sha ? repo.commit_sha.slice(0, 7) : "HEAD"}`;

  return (
    <div className="h-screen w-full flex flex-col bg-neutral-950 overflow-hidden font-sans">
      {/* Top Bar / Breadcrumb */}
      <div className="h-9 bg-neutral-900 border-b border-neutral-800 flex items-center justify-between px-3 shrink-0 text-xs text-neutral-300 select-none">
        <div className="flex items-center gap-2">
          <Link
            to={`/repos/${repo.id}`}
            title="Return to Dependency Map"
            className="flex items-center gap-1.5 text-neutral-400 hover:text-orange-400 transition-colors"
          >
            <span className="font-semibold text-neutral-200">BodhCode</span>
            <span>/</span>
            <span className="font-mono text-neutral-300">{repo.name}</span>
          </Link>
          <span>/</span>
          <span className="text-neutral-400">Editor</span>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setIsQuickOpen(true)}
            className="px-2 py-1 rounded bg-neutral-800 hover:bg-neutral-700 text-neutral-300 flex items-center gap-2 cursor-pointer text-[11px]"
          >
            <span>Search files</span>
            <kbd className="px-1 py-0.2 rounded bg-neutral-900 text-neutral-400 font-mono text-[9px]">
              Ctrl+P
            </kbd>
          </button>

          <button
            type="button"
            onClick={() => setIsBottomOpen(!isBottomOpen)}
            className={`px-2 py-1 rounded text-[11px] font-medium transition-colors cursor-pointer ${
              isBottomOpen ? "bg-orange-500/20 text-orange-300" : "bg-neutral-800 text-neutral-400 hover:text-neutral-200"
            }`}
          >
            Bottom Panel (Ctrl+J)
          </button>

          <button
            type="button"
            onClick={() => setIsAiOpen(!isAiOpen)}
            className={`px-2 py-1 rounded text-[11px] font-medium transition-colors cursor-pointer ${
              isAiOpen ? "bg-orange-500/20 text-orange-300" : "bg-neutral-800 text-neutral-400 hover:text-neutral-200"
            }`}
          >
            AI Assistant
          </button>
        </div>
      </div>

      {/* Main Workspace Layout */}
      <div className="flex-1 flex overflow-hidden">
        {/* Activity Bar */}
        <ActivityBar
          activeView={sidebarView}
          onSelectView={(view) => {
            if (sidebarView === view) {
              setSidebarView(null);
            } else {
              setSidebarView(view);
            }
          }}
          changesCount={changes.length}
          repoId={repo.id}
        />

        {/* Resizable Horizontal Panels */}
        <div className="flex-1 overflow-hidden">
          <Group
            orientation="horizontal"
            defaultLayout={savedHorizontalLayout}
            onLayoutChanged={(layout) => {
              try {
                localStorage.setItem("bodhcode.editor.layout.horizontal", JSON.stringify(layout));
              } catch {
                // Ignore restricted storage
              }
            }}
          >
            {/* Left Sidebar Panel */}
            {sidebarView && (
              <>
                <Panel id="sidebar" defaultSize={22} minSize={14} maxSize={40}>
                  <FileExplorer
                    files={files}
                    activeFilePath={tabState.activePath}
                    onOpenFile={handleOpenFile}
                    onCreateFile={handleCreateFile}
                    onRenameFile={handleRenameFile}
                    onDeleteFile={handleDeleteFile}
                    onRevertFile={handleRevertFile}
                    repoId={repo.id}
                    sidebarView={sidebarView}
                    onOpenDiff={handleOpenDiff}
                  />
                </Panel>
                <Separator className="w-1 bg-neutral-800 hover:bg-orange-500 transition-colors cursor-col-resize shrink-0" />
              </>
            )}

            {/* Center Area: Editor + Bottom Panel */}
            <Panel id="center" minSize={30}>
              <Group
                orientation="vertical"
                defaultLayout={savedVerticalLayout}
                onLayoutChanged={(layout) => {
                  try {
                    localStorage.setItem("bodhcode.editor.layout.vertical", JSON.stringify(layout));
                  } catch {
                    // Ignore restricted storage
                  }
                }}
              >
                {/* Editor Tabs & Monaco Pane */}
                <Panel id="editor" minSize={30}>
                  <div className="h-full flex flex-col overflow-hidden bg-neutral-950">
                    <EditorTabs
                      tabs={tabState.tabs}
                      activePath={tabState.activePath}
                      onSelectTab={(path) => handleOpenFile(path)}
                      onCloseTab={handleCloseTab}
                      onCloseOthers={handleCloseOthers}
                    />

                    <div className="flex-1 overflow-hidden relative">
                      <MonacoEditorPane
                        activeTab={activeTab}
                        onChangeContent={(content) => {
                          if (activeTab) {
                            dispatch({
                              type: "SET_CONTENT",
                              payload: { path: activeTab.path, content },
                            });
                          }
                        }}
                        onSave={handleSave}
                        onCursorChange={setCursorPos}
                        theme={editorTheme}
                        saveStatus={saveStatus}
                        errorMessage={
                          saveErrorMessage ||
                          (activeContentError instanceof Error
                            ? activeContentError.message
                            : null)
                        }
                        onAskAiWithSelection={(sel) => {
                          setPendingSelection(sel);
                          setIsAiOpen(true);
                        }}
                      />
                    </div>
                  </div>
                </Panel>

                {/* Bottom Panel (Changes / Problems) */}
                {isBottomOpen && (
                  <>
                    <Separator className="h-1 bg-neutral-800 hover:bg-orange-500 transition-colors cursor-row-resize shrink-0" />
                    <Panel id="bottom" defaultSize={30} minSize={15} maxSize={60}>
                      <BottomPanel
                        changes={changes}
                        activeDiffPath={diffPath}
                        diffData={diffData || null}
                        isDiffLoading={isDiffLoading}
                        onSelectDiffFile={(path) => setDiffPath(path)}
                        onRevertFile={handleRevertFile}
                        onClosePanel={() => setIsBottomOpen(false)}
                        onOpenPushModal={() => setIsPushModalOpen(true)}
                        theme={editorTheme}
                      />
                    </Panel>
                  </>
                )}
              </Group>
            </Panel>

            {/* Right Panel: AI Assistant */}
            {isAiOpen && repo && (
              <>
                <Separator className="w-1 bg-neutral-800 hover:bg-orange-500 transition-colors cursor-col-resize shrink-0" />
                <Panel id="ai" defaultSize={24} minSize={18} maxSize={45}>
                  <AgentPanel
                    repoId={repo.id}
                    activeFilePath={tabState.activePath}
                    pendingSelection={pendingSelection}
                    onClearSelection={() => setPendingSelection(null)}
                    onOpenFile={handleOpenFile}
                    onClose={() => setIsAiOpen(false)}
                    theme={editorTheme}
                    onFileModified={() => {
                      if (tabState.activePath) {
                        const currentTab = tabState.tabs.find((t) => t.path === tabState.activePath);
                        if (!currentTab?.dirty) {
                          queryClient.invalidateQueries({
                            queryKey: ["files", repo.id, "content", tabState.activePath],
                          });
                        }
                      }
                      queryClient.invalidateQueries({ queryKey: ["files", repo.id, "tree"] });
                      queryClient.invalidateQueries({ queryKey: ["files", repo.id, "changes"] });
                    }}
                  />
                </Panel>
              </>
            )}
          </Group>
        </div>
      </div>

      {/* Bottom Status Bar */}
      <StatusBar
        language={activeContentData?.language_hint || null}
        cursorPos={cursorPos}
        changesCount={changes.length}
        repoIdentifier={repoIdentifier}
      />

      {/* Quick Open Ctrl+P Modal */}
      <QuickOpenModal
        isOpen={isQuickOpen}
        onClose={() => setIsQuickOpen(false)}
        files={files}
        onSelectFile={handleOpenFile}
      />

      {/* Push to GitHub Wizard Modal */}
      {repo && (
        <PushModalWizard
          isOpen={isPushModalOpen}
          onClose={() => setIsPushModalOpen(false)}
          repoId={repo.id}
          upstreamRepo={`${repo.owner}/${repo.name}`}
          changes={changes}
          userPreferredLanguage={user?.preferred_language || "en"}
          onSuccess={() => {
            queryClient.invalidateQueries({ queryKey: ["files", repo.id, "changes"] });
            queryClient.invalidateQueries({ queryKey: ["files", repo.id, "tree"] });
          }}
        />
      )}
    </div>
  );
}
