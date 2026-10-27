import { Link } from "react-router-dom";

export type SidebarView = "explorer" | "changes" | "search";

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

        {/* Changes icon */}
        <button
          type="button"
          onClick={() => onSelectView("changes")}
          title="Working Tree Changes"
          aria-label="Working Tree Changes"
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
      </div>

      {/* Bottom map link */}
      <div className="w-full flex flex-col items-center gap-2">
        <Link
          to={`/repos/${repoId}`}
          title="Return to Dependency Map"
          aria-label="Return to Dependency Map"
          className="w-10 h-10 rounded flex items-center justify-center text-neutral-400 hover:text-orange-400 hover:bg-neutral-800/60 transition-colors"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.75}
              d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7"
            />
          </svg>
        </Link>
      </div>
    </div>
  );
}
