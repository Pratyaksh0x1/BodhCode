import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { IssuesTab } from "./IssuesTab";
import { PullRequestsTab } from "./PullRequestsTab";
import { ReadmeTab } from "./ReadmeTab";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe("Translation Content Tabs", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe("ReadmeTab", () => {
    it("renders translated README with badge and toggles original", async () => {
      vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
        const url = String(input);
        if (url.includes("/meta/languages")) {
          return {
            ok: true,
            status: 200,
            json: async () => [
              { code: "en", name: "English", english_name: "English", rtl: false },
              { code: "es", name: "Español", english_name: "Spanish", rtl: false },
            ],
          } as Response;
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            file_name: "README.md",
            original: "# Hello World\nWelcome to our repo.",
            translated: "# Hola Mundo\nBienvenido a nuestro repositorio.",
            source_lang: "en",
            target_lang: "es",
            translated_ok: true,
            reason: null,
          }),
        } as Response;
      });

      render(<ReadmeTab repoId="repo-123" preferredLanguage="es" />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText(/Translated from English → Spanish/i)).toBeInTheDocument();
      });

      expect(screen.getByText("Hola Mundo")).toBeInTheDocument();

      // Click "Show original"
      const toggleBtn = screen.getByRole("button", { name: /show original/i });
      fireEvent.click(toggleBtn);

      expect(screen.getByText("Hello World")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /show translation/i })).toBeInTheDocument();
    });

    it("displays busy warning and retry button when rate limited with reason=busy", async () => {
      vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
        const url = String(input);
        if (url.includes("/meta/languages")) {
          return {
            ok: true,
            status: 200,
            json: async () => [],
          } as Response;
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            file_name: "README.md",
            original: "# Fallback Original",
            translated: null,
            source_lang: "en",
            target_lang: "es",
            translated_ok: false,
            reason: "busy",
          }),
        } as Response;
      });

      render(<ReadmeTab repoId="repo-123" preferredLanguage="es" />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(
          screen.getByText(/Translation is busy — showing the original/i)
        ).toBeInTheDocument();
      });

      expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
    });
  });

  describe("IssuesTab", () => {
    it("renders issue items with translated title and original subtitle", async () => {
      vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
        const url = String(input);
        if (url.includes("/meta/languages")) {
          return {
            ok: true,
            status: 200,
            json: async () => [
              { code: "en", name: "English", english_name: "English", rtl: false },
              { code: "es", name: "Español", english_name: "Spanish", rtl: false },
            ],
          } as Response;
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            items: [
              {
                number: 42,
                title: "Error en el analizador",
                original_title: "Bug in parser",
                translated_title: "Error en el analizador",
                state: "open",
                author: {
                  login: "octocat",
                  avatar_url: "https://avatar.url/1.png",
                },
                created_at: "2026-10-25T10:00:00Z",
                updated_at: null,
                labels: [{ name: "bug", color: "d73a4a" }],
                comment_count: 2,
                html_url: "https://github.com/foo/bar/issues/42",
              },
            ],
            source_lang: "en",
            target_lang: "es",
            next_page: null,
          }),
        } as Response;
      });

      render(<IssuesTab repoId="repo-123" preferredLanguage="es" />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText("Error en el analizador")).toBeInTheDocument();
      });

      expect(screen.getByText("Orig: Bug in parser")).toBeInTheDocument();
      expect(screen.getByText("Translated")).toBeInTheDocument();
    });
  });

  describe("PullRequestsTab", () => {
    it("renders pull requests with translated title", async () => {
      vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
        const url = String(input);
        if (url.includes("/meta/languages")) {
          return {
            ok: true,
            status: 200,
            json: async () => [
              { code: "en", name: "English", english_name: "English", rtl: false },
              { code: "es", name: "Español", english_name: "Spanish", rtl: false },
            ],
          } as Response;
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            items: [
              {
                number: 101,
                title: "Agregar capa de traducción",
                original_title: "Add translation layer",
                translated_title: "Agregar capa de traducción",
                state: "open",
                author: {
                  login: "monalisa",
                  avatar_url: "https://avatar.url/2.png",
                },
                created_at: "2026-10-26T12:00:00Z",
                updated_at: null,
                labels: [],
                comment_count: 5,
                html_url: "https://github.com/foo/bar/pull/101",
              },
            ],
            source_lang: "en",
            target_lang: "es",
            next_page: null,
          }),
        } as Response;
      });

      render(<PullRequestsTab repoId="repo-123" preferredLanguage="es" />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText("Agregar capa de traducción")).toBeInTheDocument();
      });

      expect(screen.getByText("Orig: Add translation layer")).toBeInTheDocument();
      expect(screen.getByText("Translated")).toBeInTheDocument();
    });
  });
});
