import { create } from "zustand";
import {
  ancestorsOf,
  canExpandAll,
  canExpandFolder,
} from "../lib/graphView";
import type { BlastResult, GraphDoc } from "../lib/repos";

export interface GraphStoreState {
  expandedFolders: Set<string>;
  selectedFileId: string | null;
  blast: BlastResult | null;
  search: string;
  edgeKindsVisible: Record<string, boolean>;
  hideTypeOnly: boolean;
  tooManyNodesBanner: boolean;
  isChatOpen: boolean;

  // Actions
  initExpanded: (expanded: Set<string>) => void;
  toggleFolder: (folderId: string, graph: GraphDoc) => void;
  expandPathTo: (fileId: string) => void;
  select: (fileId: string | null) => void;
  setBlast: (blast: BlastResult | null) => void;
  clearBlast: () => void;
  setSearch: (query: string) => void;
  toggleEdgeKind: (kind: string) => void;
  toggleHideTypeOnly: () => void;
  expandAll: (graph: GraphDoc) => void;
  collapseAll: () => void;
  dismissBanner: () => void;
  toggleChat: () => void;
  setChatOpen: (open: boolean) => void;
  reset: () => void;
}

const DEFAULT_EDGE_KINDS: Record<string, boolean> = {
  import: true,
  reexport: true,
  dynamic: true,
  require: true,
};

export const useGraphStore = create<GraphStoreState>((set, get) => ({
  expandedFolders: new Set<string>(),
  selectedFileId: null,
  blast: null,
  search: "",
  edgeKindsVisible: { ...DEFAULT_EDGE_KINDS },
  hideTypeOnly: false,
  tooManyNodesBanner: false,
  isChatOpen: false,

  initExpanded: (expanded) => {
    set({ expandedFolders: new Set(expanded) });
  },

  toggleFolder: (folderId, graph) => {
    const { expandedFolders } = get();
    const next = new Set(expandedFolders);

    if (next.has(folderId)) {
      next.delete(folderId);
      set({ expandedFolders: next, tooManyNodesBanner: false });
    } else {
      if (canExpandFolder(folderId, graph, expandedFolders)) {
        next.add(folderId);
        set({ expandedFolders: next, tooManyNodesBanner: false });
      } else {
        set({ tooManyNodesBanner: true });
      }
    }
  },

  expandPathTo: (fileId) => {
    const ancestors = ancestorsOf(fileId);
    if (ancestors.length === 0) return;

    const { expandedFolders } = get();
    const next = new Set(expandedFolders);
    for (const anc of ancestors) {
      next.add(anc);
    }
    set({ expandedFolders: next });
  },

  select: (fileId) => {
    set({ selectedFileId: fileId });
  },

  setBlast: (blast) => {
    set({ blast });
  },

  clearBlast: () => {
    set({ blast: null });
  },

  setSearch: (search) => {
    set({ search });
  },

  toggleEdgeKind: (kind) => {
    const { edgeKindsVisible } = get();
    const current = edgeKindsVisible[kind] ?? true;
    set({
      edgeKindsVisible: {
        ...edgeKindsVisible,
        [kind]: !current,
      },
    });
  },

  toggleHideTypeOnly: () => {
    set((state) => ({ hideTypeOnly: !state.hideTypeOnly }));
  },

  expandAll: (graph) => {
    if (canExpandAll(graph)) {
      const allFolders = new Set(graph.folders.map((f) => f.id));
      set({ expandedFolders: allFolders, tooManyNodesBanner: false });
    } else {
      set({ tooManyNodesBanner: true });
    }
  },

  collapseAll: () => {
    set({ expandedFolders: new Set(), tooManyNodesBanner: false });
  },

  dismissBanner: () => {
    set({ tooManyNodesBanner: false });
  },

  toggleChat: () => {
    set((state) => ({ isChatOpen: !state.isChatOpen }));
  },

  setChatOpen: (open: boolean) => {
    set({ isChatOpen: open });
  },

  reset: () => {
    set({
      expandedFolders: new Set(),
      selectedFileId: null,
      blast: null,
      search: "",
      edgeKindsVisible: { ...DEFAULT_EDGE_KINDS },
      hideTypeOnly: false,
      tooManyNodesBanner: false,
      isChatOpen: false,
    });
  },
}));
