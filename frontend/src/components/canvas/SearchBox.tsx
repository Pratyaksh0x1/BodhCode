import { memo, useEffect, useMemo, useRef, useState } from "react";
import { useReactFlow } from "@xyflow/react";
import { useGraphStore } from "../../store/graphStore";
import { useGraphContext } from "./GraphContext";

export const SearchBox = memo(function SearchBox() {
  const graph = useGraphContext();
  const search = useGraphStore((s) => s.search);
  const setSearch = useGraphStore((s) => s.setSearch);
  const expandPathTo = useGraphStore((s) => s.expandPathTo);
  const select = useGraphStore((s) => s.select);
  const { fitView } = useReactFlow();

  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Global Ctrl+K / Cmd+K listener
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inputRef.current?.focus();
        setIsOpen(true);
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Filter matching files/folders
  const matches = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return [];

    const fileMatches = graph.nodes
      .filter((n) => n.id.toLowerCase().includes(q))
      .slice(0, 12);

    return fileMatches;
  }, [graph.nodes, search]);

  const handleSelect = (fileId: string) => {
    expandPathTo(fileId);
    select(fileId);
    setIsOpen(false);

    // Wait for React Flow to mount expanded nodes, then center
    setTimeout(() => {
      fitView({
        nodes: [{ id: fileId }],
        duration: 400,
        maxZoom: 1.25,
      });
    }, 60);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (matches.length > 0) {
        setHighlightedIndex((prev) => (prev + 1) % matches.length);
        setIsOpen(true);
      }
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (matches.length > 0) {
        setHighlightedIndex((prev) => (prev - 1 + matches.length) % matches.length);
        setIsOpen(true);
      }
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (matches.length > 0) {
        const chosen = matches[highlightedIndex] || matches[0];
        if (chosen) {
          handleSelect(chosen.id);
        }
      }
    } else if (e.key === "Escape") {
      setIsOpen(false);
      inputRef.current?.blur();
    }
  };

  return (
    <div
      ref={containerRef}
      className="relative z-40 w-72 select-none"
      id="canvas-search-box"
    >
      <div className="relative flex items-center">
        <svg
          className="w-4 h-4 text-neutral-400 absolute left-3 pointer-events-none"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
          />
        </svg>

        <input
          ref={inputRef}
          type="text"
          value={search}
          placeholder="Search files... (Ctrl+K)"
          aria-label="Search files in dependency graph"
          aria-autocomplete="list"
          onChange={(e) => {
            setSearch(e.target.value);
            setHighlightedIndex(0);
            setIsOpen(true);
          }}
          onFocus={() => setIsOpen(Boolean(search.trim()))}
          onKeyDown={handleKeyDown}
          className="w-full pl-9 pr-16 py-1.5 bg-white/90 dark:bg-neutral-900/90 backdrop-blur-md border border-neutral-200 dark:border-neutral-800 rounded-xl text-xs text-neutral-900 dark:text-neutral-100 placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-orange-500/60 shadow-lg transition-all"
        />

        <kbd className="absolute right-2 px-1.5 py-0.5 text-[10px] font-mono text-neutral-400 dark:text-neutral-500 bg-neutral-100 dark:bg-neutral-800 rounded border border-neutral-300 dark:border-neutral-700 pointer-events-none">
          Ctrl K
        </kbd>
      </div>

      {isOpen && matches.length > 0 && (
        <ul
          role="listbox"
          className="absolute left-0 right-0 mt-1.5 max-h-60 overflow-y-auto bg-white/95 dark:bg-neutral-900/95 backdrop-blur-md border border-neutral-200 dark:border-neutral-800 rounded-xl shadow-2xl py-1 text-xs z-50 divide-y divide-neutral-100 dark:divide-neutral-800/60"
        >
          {matches.map((item, idx) => {
            const isHighlighted = idx === highlightedIndex;
            return (
              <li
                key={item.id}
                role="option"
                aria-selected={isHighlighted}
                onClick={() => handleSelect(item.id)}
                onMouseEnter={() => setHighlightedIndex(idx)}
                className={`px-3 py-2 cursor-pointer flex flex-col gap-0.5 transition-colors ${
                  isHighlighted
                    ? "bg-orange-50 dark:bg-orange-950/40 text-orange-900 dark:text-orange-200"
                    : "text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800/50"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold truncate">{item.name}</span>
                  {item.flags?.includes("in_cycle") && (
                    <span className="text-[10px] text-amber-500">cycle</span>
                  )}
                </div>
                <span className="text-[10px] text-neutral-400 font-mono truncate">
                  {item.id}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
});
