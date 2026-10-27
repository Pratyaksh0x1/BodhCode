import { create } from "zustand";

export type ThemePref = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";
export type EditorThemePref = "auto" | "vs" | "vs-dark" | "hc-black" | "hc-light";
export type ResolvedEditorTheme = "vs" | "vs-dark" | "hc-black" | "hc-light";

export const THEME_STORAGE_KEY = "bodhcode.theme";

export interface ThemeStoreState {
  pref: ThemePref;
  resolved: ResolvedTheme;
  setThemePref: (pref: ThemePref) => void;
  setResolvedTheme: (resolved: ResolvedTheme) => void;
}

/**
 * Zustand store mirroring theme for both React hooks and non-React consumers (e.g. Monaco editor).
 */
export const useThemeStore = create<ThemeStoreState>((set) => ({
  pref: "dark",
  resolved: "dark",
  setThemePref: (pref) => set({ pref }),
  setResolvedTheme: (resolved) => set({ resolved }),
}));

/**
 * Safely retrieve theme preference from localStorage.
 */
export function getStoredTheme(): ThemePref {
  try {
    const val = localStorage.getItem(THEME_STORAGE_KEY);
    if (val === "light" || val === "dark" || val === "system") {
      return val;
    }
  } catch {
    // Ignore restricted storage errors
  }
  return "dark";
}

/**
 * Safely persist theme preference to localStorage.
 */
export function setStoredTheme(pref: ThemePref): void {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, pref);
  } catch {
    // Ignore restricted storage errors
  }
}

/**
 * Pure function: resolve app theme to "light" or "dark".
 */
export function resolveTheme(pref: ThemePref, systemIsDark: boolean): ResolvedTheme {
  if (pref === "dark") return "dark";
  if (pref === "light") return "light";
  return systemIsDark ? "dark" : "light";
}

/**
 * Pure function: resolve Monaco editor theme following app resolved theme or explicit choice.
 */
export function resolveEditorTheme(
  editorPref: EditorThemePref,
  appResolvedTheme: ResolvedTheme
): ResolvedEditorTheme {
  if (editorPref === "auto") {
    return appResolvedTheme === "dark" ? "vs-dark" : "vs";
  }
  return editorPref;
}

let activeMediaCleanup: (() => void) | null = null;

/**
 * Apply theme to document element, toggling the 'dark' class and setting 'color-scheme'.
 * If pref is 'system', subscribes to OS changes and updates live.
 */
export function applyTheme(pref: ThemePref): ResolvedTheme {
  if (activeMediaCleanup) {
    activeMediaCleanup();
    activeMediaCleanup = null;
  }

  if (typeof window === "undefined" || typeof document === "undefined") {
    return resolveTheme(pref, true);
  }

  const mediaQuery =
    typeof window.matchMedia === "function"
      ? window.matchMedia("(prefers-color-scheme: dark)")
      : null;
  const systemIsDark = mediaQuery ? mediaQuery.matches : false;
  const resolved = resolveTheme(pref, systemIsDark);

  if (resolved === "dark") {
    document.documentElement.classList.add("dark");
  } else {
    document.documentElement.classList.remove("dark");
  }
  document.documentElement.style.colorScheme = resolved;

  // Mirror into Zustand store
  useThemeStore.getState().setThemePref(pref);
  useThemeStore.getState().setResolvedTheme(resolved);

  if (pref === "system" && mediaQuery) {
    const listener = (e: MediaQueryListEvent) => {
      const liveResolved = resolveTheme("system", e.matches);
      if (liveResolved === "dark") {
        document.documentElement.classList.add("dark");
      } else {
        document.documentElement.classList.remove("dark");
      }
      document.documentElement.style.colorScheme = liveResolved;
      useThemeStore.getState().setResolvedTheme(liveResolved);
    };

    mediaQuery.addEventListener("change", listener);
    activeMediaCleanup = () => {
      mediaQuery.removeEventListener("change", listener);
    };
  }

  return resolved;
}
