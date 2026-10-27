/**
 * Pure state reducer for Monaco Editor tab management.
 */

export interface EditorTab {
  path: string;
  title: string;
  content: string;
  savedContent: string;
  dirty: boolean;
  contentHash: string | null;
  baseHash: string | null;
}

export interface TabState {
  tabs: EditorTab[];
  activePath: string | null;
}

export type TabAction =
  | {
      type: "OPEN_TAB";
      payload: {
        path: string;
        content?: string;
        hash?: string | null;
        baseHash?: string | null;
      };
    }
  | { type: "CLOSE_TAB"; payload: { path: string } }
  | { type: "CLOSE_OTHERS"; payload: { path: string } }
  | { type: "SET_ACTIVE"; payload: { path: string } }
  | { type: "SET_CONTENT"; payload: { path: string; content: string } }
  | { type: "MARK_SAVED"; payload: { path: string; contentHash: string } }
  | {
      type: "SET_LOADED_CONTENT";
      payload: {
        path: string;
        content: string;
        hash: string | null;
        baseHash: string | null;
      };
    };

export const initialTabState: TabState = {
  tabs: [],
  activePath: null,
};

function getFilename(path: string): string {
  const lastSlash = path.lastIndexOf("/");
  return lastSlash >= 0 ? path.slice(lastSlash + 1) : path;
}

export function tabReducer(state: TabState, action: TabAction): TabState {
  switch (action.type) {
    case "OPEN_TAB": {
      const existing = state.tabs.find((t) => t.path === action.payload.path);
      if (existing) {
        return {
          ...state,
          activePath: action.payload.path,
        };
      }

      const initialContent = action.payload.content ?? "";
      const newTab: EditorTab = {
        path: action.payload.path,
        title: getFilename(action.payload.path),
        content: initialContent,
        savedContent: initialContent,
        dirty: false,
        contentHash: action.payload.hash ?? null,
        baseHash: action.payload.baseHash ?? null,
      };

      return {
        tabs: [...state.tabs, newTab],
        activePath: action.payload.path,
      };
    }

    case "CLOSE_TAB": {
      const targetPath = action.payload.path;
      const tabIdx = state.tabs.findIndex((t) => t.path === targetPath);
      if (tabIdx === -1) return state;

      const newTabs = state.tabs.filter((t) => t.path !== targetPath);
      let newActive = state.activePath;

      if (state.activePath === targetPath) {
        if (newTabs.length === 0) {
          newActive = null;
        } else if (tabIdx < newTabs.length) {
          newActive = newTabs[tabIdx].path;
        } else {
          newActive = newTabs[newTabs.length - 1].path;
        }
      }

      return {
        tabs: newTabs,
        activePath: newActive,
      };
    }

    case "CLOSE_OTHERS": {
      const targetPath = action.payload.path;
      const keep = state.tabs.find((t) => t.path === targetPath);
      if (!keep) return state;

      return {
        tabs: [keep],
        activePath: targetPath,
      };
    }

    case "SET_ACTIVE": {
      if (state.activePath === action.payload.path) return state;
      const exists = state.tabs.some((t) => t.path === action.payload.path);
      if (!exists) return state;
      return {
        ...state,
        activePath: action.payload.path,
      };
    }

    case "SET_CONTENT": {
      const { path, content } = action.payload;
      let hasChanges = false;
      const newTabs = state.tabs.map((tab) => {
        if (tab.path === path) {
          if (tab.content === content) return tab;
          hasChanges = true;
          return {
            ...tab,
            content,
            dirty: content !== tab.savedContent,
          };
        }
        return tab;
      });

      return hasChanges ? { ...state, tabs: newTabs } : state;
    }

    case "MARK_SAVED": {
      const { path, contentHash } = action.payload;
      const newTabs = state.tabs.map((tab) => {
        if (tab.path === path) {
          return {
            ...tab,
            savedContent: tab.content,
            dirty: false,
            contentHash,
          };
        }
        return tab;
      });

      return { ...state, tabs: newTabs };
    }

    case "SET_LOADED_CONTENT": {
      const { path, content, hash, baseHash } = action.payload;
      const newTabs = state.tabs.map((tab) => {
        if (tab.path === path) {
          // If user hasn't edited yet, update content
          const isCurrentlyDirty = tab.dirty;
          return {
            ...tab,
            content: isCurrentlyDirty ? tab.content : content,
            savedContent: content,
            dirty: isCurrentlyDirty ? tab.content !== content : false,
            contentHash: hash,
            baseHash,
          };
        }
        return tab;
      });

      return { ...state, tabs: newTabs };
    }

    default:
      return state;
  }
}
