import { useRef } from "react";
import type { EditorTab } from "./tabState";

interface EditorTabsProps {
  tabs: EditorTab[];
  activePath: string | null;
  onSelectTab: (path: string) => void;
  onCloseTab: (path: string) => void;
  onCloseOthers: (path: string) => void;
}

export function EditorTabs({
  tabs,
  activePath,
  onSelectTab,
  onCloseTab,
  onCloseOthers,
}: EditorTabsProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  if (tabs.length === 0) {
    return null;
  }

  return (
    <div
      ref={containerRef}
      className="flex items-center bg-neutral-900 border-b border-neutral-800 overflow-x-auto no-scrollbar select-none shrink-0"
    >
      {tabs.map((tab) => {
        const isActive = tab.path === activePath;
        return (
          <div
            key={tab.path}
            onClick={() => onSelectTab(tab.path)}
            onMouseDown={(e) => {
              // Middle-click closes tab (button 1)
              if (e.button === 1) {
                e.preventDefault();
                onCloseTab(tab.path);
              }
            }}
            onContextMenu={(e) => {
              e.preventDefault();
              onCloseOthers(tab.path);
            }}
            title={`${tab.path} (Right-click to Close Others, Middle-click to Close)`}
            className={`group relative flex items-center gap-2 px-3 py-2 text-xs border-r border-neutral-800 cursor-pointer transition-colors shrink-0 max-w-56 ${
              isActive
                ? "bg-neutral-950 text-neutral-100 border-t-2 border-t-orange-500 font-medium"
                : "bg-neutral-900/80 text-neutral-400 hover:bg-neutral-850 hover:text-neutral-200"
            }`}
          >
            <span className="truncate">{tab.title}</span>

            {/* Dirty dot or Close Button */}
            <div className="flex items-center shrink-0 w-4 h-4 justify-center">
              {tab.dirty ? (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onCloseTab(tab.path);
                  }}
                  title="Unsaved changes - click to close"
                  className="w-2.5 h-2.5 rounded-full bg-orange-400 group-hover:hidden"
                />
              ) : null}

              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onCloseTab(tab.path);
                }}
                title="Close Tab"
                className={`p-0.5 rounded text-neutral-400 hover:text-neutral-100 hover:bg-neutral-800 ${
                  tab.dirty ? "hidden group-hover:block" : "opacity-0 group-hover:opacity-100"
                }`}
              >
                ✕
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
