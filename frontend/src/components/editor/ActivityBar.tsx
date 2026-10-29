import { Link } from "react-router-dom";

export type SidebarView =
  | "explorer"
  | "changes"
  | "search"
  | "mapping"
  | "run"
  | "extensions"
  | "browser"
  | "multilingual";

interface ActivityBarProps {
  activeView: SidebarView | null;
  onSelectView: (view: SidebarView) => void;
  changesCount: number;
  repoId: string | number;
}

export function ActivityBar({
  activeView,
  onSelectView,
  changesCount,
  repoId,
}: ActivityBarProps) {
  return (
    <div className="w-12 bg-neutral-900 border-r border-neutral-800 flex flex-col justify-between items-center py-2 shrink-0 select-none z-10">
      {/* Top action icons */}
      <div className="flex flex-col items-center gap-1 w-full">
        {/* Explorer icon */}
        <button
          type="button"
          onClick={() => onSelectView("explorer")}
          title="Explorer (Ctrl+B)"
          aria-label="Explorer (Ctrl+B)"
          className={`relative w-10 h-10 rounded flex items-center justify-center transition-colors cursor-pointer ${
            activeView === "explorer"
              ? "text-orange-400 bg-neutral-800/80 border-l-2 border-orange-500 rounded-l-none"
              : "text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800/40"
          }`}
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.75}
              d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
            />
          </svg>
        </button>

        {/* Search icon */}
        <button
          type="button"
          onClick={() => onSelectView("search")}
          title="Search Files"
          aria-label="Search Files"
          className={`relative w-10 h-10 rounded flex items-center justify-center transition-colors cursor-pointer ${
            activeView === "search"
              ? "text-orange-400 bg-neutral-800/80 border-l-2 border-orange-500 rounded-l-none"
              : "text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800/40"
          }`}
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.75}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
        </button>

        {/* Source Control / Changes icon */}
        <button
          type="button"
          onClick={() => onSelectView("changes")}
          title="Source Control (Changes)"
          aria-label="Source Control (Changes)"
          className={`relative w-10 h-10 rounded flex items-center justify-center transition-colors cursor-pointer ${
            activeView === "changes"
              ? "text-orange-400 bg-neutral-800/80 border-l-2 border-orange-500 rounded-l-none"
              : "text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800/40"
          }`}
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.75}
              d="M8 7v8a2 2 0 002 2h6M8 7a2 2 0 100-4 2 2 0 000 4zm8 10a2 2 0 100-4 2 2 0 000 4zm0-10a2 2 0 100-4 2 2 0 000 4z"
            />
          </svg>
          {changesCount > 0 && (
            <span className="absolute top-1.5 right-1.5 bg-orange-500 text-neutral-950 font-bold text-[9px] min-w-3.5 h-3.5 px-0.5 rounded-full flex items-center justify-center">
              {changesCount}
            </span>
          )}
        </button>

        {/* Run & Debug */}
        <button
          type="button"
          onClick={() => onSelectView("run")}
          title="Run & Debug"
          aria-label="Run & Debug"
          className={`relative w-10 h-10 rounded flex items-center justify-center transition-colors cursor-pointer ${
            activeView === "run"
              ? "text-orange-400 bg-neutral-800/80 border-l-2 border-orange-500 rounded-l-none"
              : "text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800/40"
          }`}
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.75}
              d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"
            />
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.75}
              d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
        </button>

        {/* Extensions Manager */}
        <button
          type="button"
          onClick={() => onSelectView("extensions")}
          title="Extensions (Ctrl+Shift+X)"
          aria-label="Extensions"
          className={`relative w-10 h-10 rounded flex items-center justify-center transition-colors cursor-pointer ${
            activeView === "extensions"
              ? "text-orange-400 bg-neutral-800/80 border-l-2 border-orange-500 rounded-l-none"
              : "text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800/40"
          }`}
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.75}
              d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
            />
          </svg>
        </button>

        {/* GitHub Mapping (First-Class Feature in Slide Bar!) */}
        <button
          type="button"
          onClick={() => onSelectView("mapping")}
          title="GitHub Mapping & AST Architecture"
          aria-label="GitHub Mapping & AST Architecture"
          className={`relative w-10 h-10 rounded flex items-center justify-center transition-colors cursor-pointer ${
            activeView === "mapping"
              ? "text-orange-400 bg-neutral-800/80 border-l-2 border-orange-500 rounded-l-none"
              : "text-neutral-400 hover:text-orange-400 hover:bg-neutral-800/40"
          }`}
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.75}
              d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7"
            />
          </svg>
        </button>

        {/* Embedded Browser icon */}
        <button
          type="button"
          onClick={() => onSelectView("browser")}
          title="Embedded Local Browser"
          aria-label="Embedded Local Browser"
          className={`relative w-10 h-10 rounded flex items-center justify-center transition-colors cursor-pointer ${
            activeView === "browser"
              ? "text-orange-400 bg-neutral-800/80 border-l-2 border-orange-500 rounded-l-none"
              : "text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800/40"
          }`}
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.75}
              d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9"
            />
          </svg>
        </button>

        {/* Multilingual Repo Reader icon */}
        <button
          type="button"
          onClick={() => onSelectView("multilingual")}
          title="Multilingual Repo Reader"
          aria-label="Multilingual Repo Reader"
          className={`relative w-10 h-10 rounded flex items-center justify-center transition-colors cursor-pointer ${
            activeView === "multilingual"
              ? "text-orange-400 bg-neutral-800/80 border-l-2 border-orange-500 rounded-l-none"
              : "text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800/40"
          }`}
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.75}
              d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129"
            />
          </svg>
        </button>
      </div>

      {/* Bottom map link */}
      <div className="w-full flex flex-col items-center gap-2">
        <Link
          to={`/repos/${repoId}`}
          title="Open Full 2D Dependency Canvas"
          aria-label="Open Full 2D Dependency Canvas"
          className="w-10 h-10 rounded flex items-center justify-center text-neutral-400 hover:text-orange-400 hover:bg-neutral-800/60 transition-colors"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.75}
              d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
            />
          </svg>
        </Link>
      </div>
    </div>
  );
}
