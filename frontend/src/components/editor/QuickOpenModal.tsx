import { useEffect, useMemo, useRef, useState } from "react";
import type { RepoFileItem } from "../../lib/files";
import { fuzzySearch } from "../../lib/fuzzy";

interface QuickOpenModalProps {
  isOpen: boolean;
  onClose: () => void;
  files: RepoFileItem[];
  onSelectFile: (path: string) => void;
}

export function QuickOpenModal({
  isOpen,
  onClose,
  files,
  onSelectFile,
}: QuickOpenModalProps) {
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen) {
      inputRef.current?.focus();
    }
  }, [isOpen]);

  const matches = useMemo(() => {
    if (!isOpen) return [];
    const paths = files.map((f) => f.path);
    const scored = fuzzySearch(query, paths);
    return scored.slice(0, 30).map((m) => {
      const file = files.find((f) => f.path === m.path);
      return {
        path: m.path,
        score: m.score,
        status: file?.status,
        graphNode: file?.graph_node,
      };
    });
  }, [isOpen, query, files]);

  const handleClose = () => {
    setQuery("");
    setSelectedIndex(0);
    onClose();
  };

  // Keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      handleClose();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => (matches.length > 0 ? (prev + 1) % matches.length : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) =>
        matches.length > 0 ? (prev - 1 + matches.length) % matches.length : 0
      );
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (matches[selectedIndex]) {
        onSelectFile(matches[selectedIndex].path);
        onClose();
      }
    }
  };

  if (!isOpen) return null;

  return (
    <div
      onClick={handleClose}
      className="fixed inset-0 bg-black/60 backdrop-blur-xs flex items-start justify-center pt-24 z-50 p-4"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-xl bg-neutral-900 border border-neutral-700 rounded-xl shadow-2xl flex flex-col overflow-hidden"
      >
        {/* Search Input */}
        <div className="flex items-center gap-2 px-3 py-2.5 border-b border-neutral-800 bg-neutral-950">
          <svg className="w-4 h-4 text-neutral-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelectedIndex(0);
            }}
            onKeyDown={handleKeyDown}
            placeholder="Type to search files by name (e.g. 'compo btn')..."
            className="flex-1 bg-transparent text-sm text-neutral-100 placeholder-neutral-500 focus:outline-none"
          />
          <kbd className="px-1.5 py-0.5 rounded bg-neutral-800 text-neutral-400 font-mono text-[10px]">
            ESC
          </kbd>
        </div>

        {/* Results List */}
        <div ref={listRef} className="max-h-80 overflow-y-auto divide-y divide-neutral-900/60 py-1">
          {matches.length === 0 ? (
            <div className="p-4 text-center text-xs text-neutral-500">No matching files found</div>
          ) : (
            matches.map((item, idx) => {
              const isSelected = idx === selectedIndex;
              const lastSlash = item.path.lastIndexOf("/");
              const folder = lastSlash >= 0 ? item.path.slice(0, lastSlash) : "";
              const filename = lastSlash >= 0 ? item.path.slice(lastSlash + 1) : item.path;

              return (
                <div
                  key={item.path}
                  onClick={() => {
                    onSelectFile(item.path);
                    onClose();
                  }}
                  onMouseEnter={() => setSelectedIndex(idx)}
                  className={`flex items-center justify-between px-3 py-2 text-xs cursor-pointer ${
                    isSelected ? "bg-orange-500/20 text-orange-200" : "text-neutral-300 hover:bg-neutral-800/40"
                  }`}
                >
                  <div className="flex items-center gap-2 overflow-hidden">
                    <span className="font-medium text-neutral-100">{filename}</span>
                    {folder && <span className="text-[11px] text-neutral-500 truncate">{folder}</span>}
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    {item.graphNode && (
                      <span className="px-1 text-[9px] rounded bg-neutral-800 text-neutral-400 border border-neutral-700">
                        Graph
                      </span>
                    )}
                    {item.status === "modified" && (
                      <span className="text-[10px] font-bold text-amber-400">M</span>
                    )}
                    {item.status === "added" && (
                      <span className="text-[10px] font-bold text-emerald-400">A</span>
                    )}
                    {item.status === "deleted" && (
                      <span className="text-[10px] font-bold text-rose-400 line-through">D</span>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
