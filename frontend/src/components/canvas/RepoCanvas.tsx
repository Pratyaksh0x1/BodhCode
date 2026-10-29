import { memo, useEffect, useMemo, useState } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  type EdgeTypes,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import type { GraphDoc } from "../../lib/repos";
import { initialExpanded, visibleEdges, visibleNodes } from "../../lib/graphView";
import { layoutWithDagre } from "../../lib/layout";
import { useGraphStore } from "../../store/graphStore";
import { FileNode } from "./FileNode";
import { FolderNode } from "./FolderNode";
import { GraphContext } from "./GraphContext";
import { KindEdge } from "./KindEdge";
import { Legend } from "./Legend";
import { SearchBox } from "./SearchBox";
import { SidePanel } from "./SidePanel";
import { TopBar } from "./TopBar";
import { ChatDrawer } from "./ChatDrawer";

// Define nodeTypes and edgeTypes outside component render to prevent React Flow re-mounts
const nodeTypes: NodeTypes = {
  folder: FolderNode,
  file: FileNode,
};

const edgeTypes: EdgeTypes = {
  default: KindEdge,
};

interface RepoCanvasInnerProps {
  repoId: number | string;
  graph: GraphDoc;
  repoStatus?: string;
}

function RepoCanvasInner({ repoId, graph, repoStatus }: RepoCanvasInnerProps) {
  const expandedFolders = useGraphStore((s) => s.expandedFolders);
  const initExpanded = useGraphStore((s) => s.initExpanded);
  const edgeKindsVisible = useGraphStore((s) => s.edgeKindsVisible);
  const hideTypeOnly = useGraphStore((s) => s.hideTypeOnly);
  const tooManyNodesBanner = useGraphStore((s) => s.tooManyNodesBanner);
  const dismissBanner = useGraphStore((s) => s.dismissBanner);
  const select = useGraphStore((s) => s.select);
  const clearBlast = useGraphStore((s) => s.clearBlast);
  const selectedFileId = useGraphStore((s) => s.selectedFileId);
  const isChatOpen = useGraphStore((s) => s.isChatOpen);
  const setChatOpen = useGraphStore((s) => s.setChatOpen);

  // Initialize auto-expanded folders on mount or repo change
  useEffect(() => {
    initExpanded(initialExpanded(graph));
  }, [graph, initExpanded]);

  // Escape key handler: clears blast first, then selection
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        const state = useGraphStore.getState();
        if (state.blast) {
          clearBlast();
        } else if (state.selectedFileId) {
          select(null);
        }
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [clearBlast, select]);

  // Theme detection for React Flow colorMode
  const [colorMode, setColorMode] = useState<"dark" | "light">(() => {
    if (typeof window === "undefined") return "dark";
    return document.documentElement.classList.contains("dark") ||
      window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  });

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (e: MediaQueryListEvent) => {
      setColorMode(e.matches ? "dark" : "light");
    };
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  // Compute visible edges
  const derivedEdges = useMemo(() => {
    const vEdges = visibleEdges(graph, expandedFolders, {
      edgeKindsVisible,
      hideTypeOnly,
    });

    return vEdges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      type: "default",
      data: {
        kinds: Array.from(e.kinds),
        count: e.count,
        typeOnlyOnly: e.typeOnlyOnly,
        typeOnly: e.typeOnly,
      },
    }));
  }, [graph, expandedFolders, edgeKindsVisible, hideTypeOnly]);

  // Compute visible nodes with fan-in / fan-out and Dagre layout
  const positionedNodes = useMemo(() => {
    const vNodes = visibleNodes(graph, expandedFolders);

    // Compute fan-in / fan-out map from raw graph edges
    const fanInMap = new Map<string, number>();
    const fanOutMap = new Map<string, number>();
    for (const edge of (graph.edges ?? [])) {
      fanOutMap.set(edge.source, (fanOutMap.get(edge.source) || 0) + 1);
      fanInMap.set(edge.target, (fanInMap.get(edge.target) || 0) + 1);
    }

    const enrichedNodes = vNodes.map((n) => ({
      ...n,
      data: {
        ...n.data,
        fanIn: fanInMap.get(n.id) || 0,
        fanOut: fanOutMap.get(n.id) || 0,
      },
    }));

    const rawVisibleEdges = visibleEdges(graph, expandedFolders, {
      edgeKindsVisible,
      hideTypeOnly,
    });

    return layoutWithDagre(enrichedNodes, rawVisibleEdges, { direction: "LR" });
  }, [graph, expandedFolders, edgeKindsVisible, hideTypeOnly]);

  return (
    <div className="w-full h-[760px] relative rounded-2xl border border-neutral-300 dark:border-neutral-800 bg-neutral-100 dark:bg-neutral-950 overflow-hidden shadow-2xl flex">
      {/* Non-blocking banner for node cap */}
      {tooManyNodesBanner && (
        <div
          id="too-many-nodes-banner"
          role="alert"
          className="absolute top-16 left-1/2 -translate-x-1/2 z-50 px-4 py-2.5 rounded-xl bg-amber-950/95 border border-amber-600/80 text-amber-200 text-xs shadow-2xl flex items-center gap-3 backdrop-blur"
        >
          <span className="font-medium">
            ⚠️ Too many nodes — collapse some folders (limit: 600 nodes)
          </span>
          <button
            type="button"
            onClick={dismissBanner}
            aria-label="Dismiss too many nodes banner"
            className="text-amber-400 hover:text-amber-100 font-bold p-1 rounded hover:bg-amber-900/40"
          >
            ✕
          </button>
        </div>
      )}

      {/* Main Canvas Area */}
      <div className="flex-1 h-full relative">
        {/* Floating Top Controls Bar */}
        <div className="absolute top-4 left-4 right-4 z-20 pointer-events-auto">
          <TopBar />
        </div>

        {/* Floating Search Box */}
        <div className="absolute top-20 left-4 z-20 pointer-events-auto">
          <SearchBox />
        </div>

        {/* Floating Legend */}
        <div className="absolute bottom-4 left-4 z-20 pointer-events-auto">
          <Legend />
        </div>

        <ReactFlow
          nodes={positionedNodes}
          edges={derivedEdges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onlyRenderVisibleElements
          fitView
          fitViewOptions={{ padding: 0.15 }}
          minZoom={0.1}
          maxZoom={2.0}
          colorMode={colorMode}
          onPaneClick={() => select(null)}
          className="w-full h-full"
        >
          <Background
            variant={BackgroundVariant.Dots}
            gap={20}
            size={1.5}
            color={colorMode === "dark" ? "#262626" : "#d4d4d4"}
          />
          <Controls position="bottom-right" className="!m-4 !border-neutral-800" />
          <MiniMap
            position="bottom-right"
            nodeColor={(node) => {
              if (node.type === "folder") return "#f59e0b";
              if (node.id === selectedFileId) return "#f97316";
              return "#38bdf8";
            }}
            className="!m-4 !mb-20 !rounded-xl !overflow-hidden !border !border-neutral-300 dark:!border-neutral-800 !bg-white/80 dark:!bg-neutral-900/80 !backdrop-blur"
          />
        </ReactFlow>
      </div>

      {/* Side Panel for Selected File */}
      {selectedFileId && <SidePanel repoId={repoId} />}

      {/* Floating Ask AI Button (visible when chat is closed) */}
      {!isChatOpen && (
        <button
          type="button"
          id="floating-ask-ai-btn"
          onClick={() => setChatOpen(true)}
          className="absolute bottom-6 right-6 z-30 px-4 py-2.5 rounded-full bg-gradient-to-r from-orange-500 to-amber-500 hover:from-orange-400 hover:to-amber-400 text-white font-bold text-xs shadow-2xl flex items-center gap-2 cursor-pointer transition-all hover:scale-105 active:scale-95"
          title="Ask questions about this repository's architecture and dependencies"
        >
          <span className="text-sm">💬</span>
          <span>Ask AI Architecture Question</span>
        </button>
      )}

      {/* AI Chat Drawer */}
      <ChatDrawer repoId={repoId} repoStatus={repoStatus} />
    </div>
  );
}

export interface RepoCanvasProps {
  repoId: number | string;
  graph: GraphDoc;
  repoStatus?: string;
}

export const RepoCanvas = memo(function RepoCanvas({
  repoId,
  graph,
  repoStatus,
}: RepoCanvasProps) {
  return (
    <GraphContext.Provider value={graph}>
      <ReactFlowProvider>
        <RepoCanvasInner repoId={repoId} graph={graph} repoStatus={repoStatus} />
      </ReactFlowProvider>
    </GraphContext.Provider>
  );
});
