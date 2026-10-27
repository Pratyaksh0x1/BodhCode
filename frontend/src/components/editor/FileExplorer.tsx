import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { FileStatus, RepoFileItem } from "../../lib/files";
import { fuzzySearch } from "../../lib/fuzzy";

interface FileExplorerProps {
  files: RepoFileItem[];
  activeFilePath: string | null;
  onOpenFile: (path: string) => void;
  onCreateFile: (path: string) => void;
  onRenameFile: (oldPath: string, newPath: string) => void;
  onDeleteFile: (path: string) => void;
  onRevertFile: (path: string) => void;
  repoId: string | number;
  sidebarView: "explorer" | "changes" | "search";
  onOpenDiff?: (path: string) => void;
}

interface TreeNode {
  name: string;
  path: string;
  isFolder: boolean;
  children?: TreeNode[];
  fileItem?: RepoFileItem;
}

function getFileIcon(filename: string): { icon: string; color: string } {
  const ext = filename.split(".").pop()?.toLowerCase();
  switch (ext) {
    case "ts":
      return { icon: "TS", color: "text-blue-400" };
    case "tsx":
      return { icon: "⚛", color: "text-sky-400" };
    case "js":
      return { icon: "JS", color: "text-yellow-400" };
    case "jsx":
      return { icon: "⚛", color: "text-yellow-300" };
    case "json":
      return { icon: "{}", color: "text-amber-400" };
    case "css":
    case "scss":
      return { icon: "#", color: "text-pink-400" };
    case "html":
      return { icon: "<>", color: "text-orange-400" };
    case "md":
    case "mdx":
      return { icon: "M↓", color: "text-indigo-400" };
    case "yml":
    case "yaml":
    case "toml":
      return { icon: "⚙", color: "text-emerald-400" };
    case "svg":
      return { icon: "✦", color: "text-amber-500" };
    default:
      return { icon: "📄", color: "text-neutral-400" };
  }
}

function getStatusBadge(status?: FileStatus) {
  switch (status) {
    case "modified":
      return <span className="text-[10px] font-bold text-amber-400">M</span>;
    case "added":
      return <span className="text-[10px] font-bold text-emerald-400">A</span>;
    case "deleted":
      return <span className="text-[10px] font-bold text-rose-400 line-through">D</span>;
    default:
      return null;
  }
}

export function FileExplorer({
  files,
  activeFilePath,
  onOpenFile,
  onCreateFile,
  onRenameFile,
  onDeleteFile,
  onRevertFile,
  repoId,
  sidebarView,
  onOpenDiff,
}: FileExplorerProps) {
  const navigate = useNavigate();
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(() => {
    const initial = new Set<string>();
    // Auto-expand ancestors of active file
    if (activeFilePath) {
      const parts = activeFilePath.split("/");
      let curr = "";
      for (let i = 0; i < parts.length - 1; i++) {
        curr = curr ? `${curr}/${parts[i]}` : parts[i];
        initial.add(curr);
      }
    }
    return initial;
  });

  const [searchQuery, setSearchQuery] = useState("");
  const [promptModal, setPromptModal] = useState<{
    type: "new" | "rename";
    targetPath?: string;
  } | null>(null);
  const [promptInput, setPromptInput] = useState("");

  const toggleFolder = (path: string) => {
    setExpandedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  };

  // Build tree from files
  const fileTree = useMemo(() => {
    const root: TreeNode = { name: "root", path: "", isFolder: true, children: [] };

    for (const file of files) {
      const parts = file.path.split("/");
      let current = root;

      for (let i = 0; i < parts.length; i++) {
        const part = parts[i];
        const isFile = i === parts.length - 1;
        const currentPath = parts.slice(0, i + 1).join("/");

        if (!current.children) {
          current.children = [];
        }

        let existing = current.children.find((c) => c.name === part);
        if (!existing) {
          existing = {
            name: part,
            path: currentPath,
            isFolder: !isFile,
            children: isFile ? undefined : [],
            fileItem: isFile ? file : undefined,
          };
          current.children.push(existing);
        }
        current = existing;
      }
    }

    // Sort folders first, then alphabetically
    const sortNodes = (node: TreeNode) => {
      if (node.children) {
        node.children.sort((a, b) => {
          if (a.isFolder === b.isFolder) {
            return a.name.localeCompare(b.name);
          }
          return a.isFolder ? -1 : 1;
        });
        node.children.forEach(sortNodes);
      }
    };
    sortNodes(root);

    return root.children || [];
  }, [files]);

  // Search filtered files
  const searchResults = useMemo(() => {
    if (sidebarView !== "search" || !searchQuery.trim()) {
      return [];
    }
    const allPaths = files.map((f) => f.path);
    const matches = fuzzySearch(searchQuery, allPaths);
    return matches.map((m) => {
      const file = files.find((f) => f.path === m.path);
      return { ...m, file };
    });
  }, [sidebarView, searchQuery, files]);

  // Changed files
  const changedFiles = useMemo(() => {
    return files.filter((f) => f.status !== "unchanged");
  }, [files]);

  const handleStartCreate = (basePath = "") => {
    setPromptInput(basePath ? `${basePath}/` : "");
    setPromptModal({ type: "new" });
  };

  const handleStartRename = (oldPath: string) => {
    setPromptInput(oldPath);
    setPromptModal({ type: "rename", targetPath: oldPath });
  };

  const handleConfirmPrompt = () => {
    if (!promptInput.trim() || !promptModal) return;
    if (promptModal.type === "new") {
      onCreateFile(promptInput.trim());
    } else if (promptModal.type === "rename" && promptModal.targetPath) {
      onRenameFile(promptModal.targetPath, promptInput.trim());
    }
    setPromptModal(null);
    setPromptInput("");
  };

  // Recursive Tree Node Renderer
  const renderTreeNode = (node: TreeNode, depth = 0) => {
    const isExpanded = expandedFolders.has(node.path);
    const isSelected = activeFilePath === node.path;
    const paddingLeft = `${depth * 14 + 10}px`;

    if (node.isFolder) {
      return (
        <div key={node.path} className="select-none">
          <div
            onClick={() => toggleFolder(node.path)}
            style={{ paddingLeft }}
            className="flex items-center justify-between pr-2 py-1 text-xs text-neutral-300 hover:bg-neutral-800/60 cursor-pointer group"
          >
            <div className="flex items-center gap-1.5 overflow-hidden">
              <span className="text-[10px] text-neutral-500 w-3 text-center">
                {isExpanded ? "▼" : "▶"}
              </span>
              <svg className="w-3.5 h-3.5 text-neutral-400 shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" />
              </svg>
              <span className="truncate">{node.name}</span>
            </div>

            <div className="opacity-0 group-hover:opacity-100 flex items-center gap-1">
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  handleStartCreate(node.path);
                }}
                title="New file in this folder"
                className="p-0.5 rounded hover:bg-neutral-700 text-neutral-400 hover:text-white"
              >
                +
              </button>
            </div>
          </div>

          {isExpanded && node.children && (
            <div>{node.children.map((child) => renderTreeNode(child, depth + 1))}</div>
          )}
        </div>
      );
    }

    const { icon, color } = getFileIcon(node.name);
    const fileStatus = node.fileItem?.status;
    const isGraphNode = node.fileItem?.graph_node;
    const isDeleted = fileStatus === "deleted";

    return (
      <div
        key={node.path}
        style={{ paddingLeft }}
        onClick={() => !isDeleted && onOpenFile(node.path)}
        className={`flex items-center justify-between pr-2 py-1 text-xs cursor-pointer group transition-colors ${
          isSelected
            ? "bg-orange-500/15 text-orange-300 font-medium border-l-2 border-orange-500"
            : "text-neutral-300 hover:bg-neutral-800/60"
        } ${isDeleted ? "opacity-50 cursor-not-allowed" : ""}`}
      >
        <div className="flex items-center gap-2 overflow-hidden">
          <span className={`font-mono text-xs font-bold shrink-0 ${color}`}>{icon}</span>
          <span className={`truncate ${isDeleted ? "line-through text-rose-400" : ""}`}>
            {node.name}
          </span>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {getStatusBadge(fileStatus)}

          <div className="opacity-0 group-hover:opacity-100 flex items-center gap-1">
            {isGraphNode && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  navigate(`/repos/${repoId}?highlight=${encodeURIComponent(node.path)}`);
                }}
                title="Show in dependency map"
                className="px-1 text-[10px] rounded bg-neutral-800 hover:bg-orange-950/60 text-orange-400 hover:text-orange-300 border border-neutral-700"
              >
                Map
              </button>
            )}

            {fileStatus && fileStatus !== "unchanged" && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onRevertFile(node.path);
                }}
                title="Revert changes"
                className="px-1 text-[10px] rounded hover:bg-neutral-700 text-amber-400"
              >
                Revert
              </button>
            )}

            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                handleStartRename(node.path);
              }}
              title="Rename file"
              className="px-1 text-[10px] rounded hover:bg-neutral-700 text-neutral-400 hover:text-white"
            >
              ✎
            </button>

            {!isDeleted && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onDeleteFile(node.path);
                }}
                title="Delete file"
                className="px-1 text-[10px] rounded hover:bg-neutral-700 text-neutral-400 hover:text-rose-400"
              >
                ✕
              </button>
            )}
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="h-full flex flex-col bg-neutral-950 text-neutral-200 select-none overflow-hidden">
      {/* View Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-neutral-800 text-[11px] font-semibold uppercase tracking-wider text-neutral-400 shrink-0">
        <span>
          {sidebarView === "explorer" && "Explorer"}
          {sidebarView === "changes" && `Changes (${changedFiles.length})`}
          {sidebarView === "search" && "Search Files"}
        </span>

        {sidebarView === "explorer" && (
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => handleStartCreate()}
              title="New File"
              className="p-1 rounded hover:bg-neutral-800 text-neutral-400 hover:text-neutral-100 cursor-pointer"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
            </button>
          </div>
        )}
      </div>

      {/* Explorer Mode */}
      {sidebarView === "explorer" && (
        <div className="flex-1 overflow-y-auto py-1">
          {fileTree.length === 0 ? (
            <div className="p-4 text-center text-xs text-neutral-500">No files in repository</div>
          ) : (
            fileTree.map((node) => renderTreeNode(node))
          )}
        </div>
      )}

      {/* Changes Mode */}
      {sidebarView === "changes" && (
        <div className="flex-1 overflow-y-auto py-1">
          {changedFiles.length === 0 ? (
            <div className="p-4 text-center text-xs text-neutral-500">
              No working-copy changes. All files match the original repository.
            </div>
          ) : (
            <div className="divide-y divide-neutral-900">
              {changedFiles.map((file) => (
                <div
                  key={file.path}
                  onClick={() => onOpenDiff ? onOpenDiff(file.path) : onOpenFile(file.path)}
                  className="flex items-center justify-between px-3 py-2 text-xs hover:bg-neutral-900/60 cursor-pointer group"
                >
                  <div className="flex items-center gap-2 overflow-hidden">
                    {getStatusBadge(file.status)}
                    <span className="truncate text-neutral-200">{file.path}</span>
                  </div>

                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onRevertFile(file.path);
                      }}
                      title="Revert file"
                      className="text-[10px] px-1.5 py-0.5 rounded bg-neutral-800 hover:bg-neutral-700 text-amber-400"
                    >
                      Revert
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Search Mode */}
      {sidebarView === "search" && (
        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="p-2 border-b border-neutral-800 shrink-0">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by file path..."
              className="w-full px-2.5 py-1.5 text-xs bg-neutral-900 border border-neutral-700 rounded text-neutral-200 placeholder-neutral-500 focus:outline-none focus:border-orange-500"
              autoFocus
            />
          </div>

          <div className="flex-1 overflow-y-auto py-1">
            {searchQuery.trim() && searchResults.length === 0 && (
              <div className="p-4 text-center text-xs text-neutral-500">No matching files found</div>
            )}
            {searchResults.map(({ path, file }) => (
              <div
                key={path}
                onClick={() => onOpenFile(path)}
                className="flex items-center justify-between px-3 py-1.5 text-xs hover:bg-neutral-800/60 cursor-pointer"
              >
                <span className="truncate text-neutral-300">{path}</span>
                {getStatusBadge(file?.status)}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Modal Prompt for New File / Rename */}
      {promptModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-xs flex items-center justify-center z-50 p-4">
          <div className="w-full max-w-sm bg-neutral-900 border border-neutral-700 rounded-xl p-4 shadow-2xl space-y-3">
            <h3 className="text-sm font-semibold text-neutral-200">
              {promptModal.type === "new" ? "Create New File" : "Rename File"}
            </h3>
            <input
              type="text"
              value={promptInput}
              onChange={(e) => setPromptInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleConfirmPrompt();
                if (e.key === "Escape") setPromptModal(null);
              }}
              placeholder="e.g. src/utils/helper.ts"
              className="w-full px-3 py-1.5 text-xs bg-neutral-950 border border-neutral-700 rounded text-neutral-100 focus:outline-none focus:border-orange-500"
              autoFocus
            />
            <div className="flex justify-end gap-2 pt-1">
              <button
                type="button"
                onClick={() => setPromptModal(null)}
                className="px-3 py-1 text-xs rounded bg-neutral-800 text-neutral-300 hover:bg-neutral-700"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmPrompt}
                className="px-3 py-1 text-xs rounded bg-orange-600 text-white font-medium hover:bg-orange-500"
              >
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
