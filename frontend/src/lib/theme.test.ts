import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  applyTheme,
  getStoredTheme,
  resolveEditorTheme,
  resolveTheme,
  setStoredTheme,
  THEME_STORAGE_KEY,
} from "./theme";

describe("theme logic", () => {
  describe("resolveTheme truth table", () => {
    it("always resolves 'dark' when pref is dark", () => {
      expect(resolveTheme("dark", true)).toBe("dark");
      expect(resolveTheme("dark", false)).toBe("dark");
    });

    it("always resolves 'light' when pref is light", () => {
      expect(resolveTheme("light", true)).toBe("light");
      expect(resolveTheme("light", false)).toBe("light");
    });

    it("follows systemIsDark when pref is system", () => {
      expect(resolveTheme("system", true)).toBe("dark");
      expect(resolveTheme("system", false)).toBe("light");
    });
  });

  describe("resolveEditorTheme truth table", () => {
    it("maps 'auto' to 'vs-dark' or 'vs' based on app theme", () => {
      expect(resolveEditorTheme("auto", "dark")).toBe("vs-dark");
      expect(resolveEditorTheme("auto", "light")).toBe("vs");
    });

    it("returns explicit editor theme choice regardless of app theme", () => {
      expect(resolveEditorTheme("vs", "dark")).toBe("vs");
      expect(resolveEditorTheme("vs-dark", "light")).toBe("vs-dark");
      expect(resolveEditorTheme("hc-black", "light")).toBe("hc-black");
      expect(resolveEditorTheme("hc-light", "dark")).toBe("hc-light");
    });
  });

  describe("localStorage safety", () => {
    beforeEach(() => {
      localStorage.clear();
    });

    it("retrieves stored valid theme or defaults to dark", () => {
      expect(getStoredTheme()).toBe("dark");
      setStoredTheme("light");
      expect(getStoredTheme()).toBe("light");
      setStoredTheme("system");
      expect(getStoredTheme()).toBe("system");
    });

    it("handles corrupted storage gracefully", () => {
      localStorage.setItem(THEME_STORAGE_KEY, "invalid-theme-value");
      expect(getStoredTheme()).toBe("dark");
    });
  });

  describe("applyTheme DOM manipulation and listeners", () => {
    let mockListeners: Array<(e: { matches: boolean }) => void> = [];
    let systemMatches = false;

    beforeEach(() => {
      mockListeners = [];
      systemMatches = false;
      document.documentElement.className = "";
      document.documentElement.style.colorScheme = "";

      // Mock window.matchMedia
      window.matchMedia = vi.fn().mockImplementation((query: string) => ({
        matches: systemMatches,
        media: query,
        onchange: null,
        addEventListener: vi.fn((event: string, handler: (e: { matches: boolean }) => void) => {
          if (event === "change") {
            mockListeners.push(handler);
          }
        }),
        removeEventListener: vi.fn((event: string, handler: (e: { matches: boolean }) => void) => {
          if (event === "change") {
            mockListeners = mockListeners.filter((l) => l !== handler);
          }
        }),
        dispatchEvent: vi.fn(),
      }));
    });

    afterEach(() => {
      document.documentElement.className = "";
      document.documentElement.style.colorScheme = "";
    });

    it("toggles 'dark' class and sets colorScheme for explicit light/dark", () => {
      applyTheme("dark");
      expect(document.documentElement.classList.contains("dark")).toBe(true);
      expect(document.documentElement.style.colorScheme).toBe("dark");

      applyTheme("light");
      expect(document.documentElement.classList.contains("dark")).toBe(false);
      expect(document.documentElement.style.colorScheme).toBe("light");
    });

    it("subscribes to matchMedia change when pref is system and updates live", () => {
      systemMatches = true;
      applyTheme("system");
      expect(document.documentElement.classList.contains("dark")).toBe(true);
      expect(mockListeners).toHaveLength(1);

      // Simulate OS switching to light
      mockListeners[0]({ matches: false });
      expect(document.documentElement.classList.contains("dark")).toBe(false);
      expect(document.documentElement.style.colorScheme).toBe("light");

      // Simulate OS switching back to dark
      mockListeners[0]({ matches: true });
      expect(document.documentElement.classList.contains("dark")).toBe(true);
      expect(document.documentElement.style.colorScheme).toBe("dark");
    });

    it("cleans up system listener when switching to explicit theme", () => {
      applyTheme("system");
      expect(mockListeners).toHaveLength(1);

      // Switching to dark cleans up listener
      applyTheme("dark");
      expect(mockListeners).toHaveLength(0);
    });
  });
});
