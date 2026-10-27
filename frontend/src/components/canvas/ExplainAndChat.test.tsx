import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactFlowProvider } from "@xyflow/react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SidePanel } from "./SidePanel";
import { ChatDrawer } from "./ChatDrawer";
import { GraphContext } from "./GraphContext";
import { useGraphStore } from "../../store/graphStore";
import type { GraphDoc } from "../../lib/repos";

const mockGraph: GraphDoc = {
  version: 1,
  repo: { owner: "testowner", name: "testrepo", commit_sha: "abcdef123" },
  nodes: [
    {
      id: "src/index.ts",
      name: "index.ts",
      folder: "src",
      size: 512,
      exports: ["main"],
      has_default_export: false,
      external_deps: [],
      unresolved_count: 0,
      unresolved_dynamic: 0,
      flags: [],
    },
    {
      id: "src/utils.ts",
      name: "utils.ts",
      folder: "src",
      size: 256,
      exports: ["helper"],
      has_default_export: false,
      external_deps: [],
      unresolved_count: 0,
      unresolved_dynamic: 0,
      flags: [],
    },
  ],
  edges: [
    {
      id: "e1",
      source: "src/index.ts",
      target: "src/utils.ts",
      kind: "import",
      type_only: false,
      count: 1,
    },
  ],
  folders: [{ id: "src", parent: "", file_count: 2 }],
  stats: {
    files: 2,
    edges: 1,
    external_packages: 0,
    cycles: 0,
    unresolved: 0,
  },
};

import { MemoryRouter } from "react-router-dom";

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <GraphContext.Provider value={mockGraph}>
          <ReactFlowProvider>{ui}</ReactFlowProvider>
        </GraphContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Explain and Chat Components", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useGraphStore.getState().reset();
  });

  describe("SidePanel Grounded Explanation", () => {
    it("renders explain button, triggers explain, and displays verified/flagged mentions", async () => {
      useGraphStore.getState().select("src/index.ts");

      vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
        const url = String(input);
        if (url.includes("/auth/me")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              id: 1,
              github_id: 12345,
              login: "testuser",
              preferred_language: "hi",
            }),
          } as Response;
        }
        if (url.includes("/meta/languages")) {
          return {
            ok: true,
            status: 200,
            json: async () => [
              { code: "hi", english_name: "Hindi", native_name: "हिन्दी", rtl: false },
            ],
          } as Response;
        }
        if (url.includes("/explain")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              explanation: "This file imports `src/utils.ts` and uses `nonexistent.ts ⚠unverified`.",
              verified_files: ["src/utils.ts"],
              flagged: ["nonexistent.ts"],
              language: "hi",
              cached: true,
            }),
          } as Response;
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({ dependencies: [], dependents: [] }),
        } as Response;
      });

      renderWithProviders(<SidePanel repoId="repo-123" />);

      // Find explain button
      const explainBtn = await screen.findByRole("button", {
        name: /Explain index\.ts/i,
      });
      expect(explainBtn).toBeInTheDocument();

      fireEvent.click(explainBtn);

      // Verify explanation result rendered
      await waitFor(() => {
        expect(screen.getByText("⚡ Cached")).toBeInTheDocument();
        expect(screen.getByText("हिन्दी")).toBeInTheDocument();
        expect(screen.getByText(/Verified Mentions/i)).toBeInTheDocument();
        expect(screen.getAllByText(/nonexistent\.ts/i).length).toBeGreaterThanOrEqual(1);
      });
    });
  });

  describe("ChatDrawer", () => {
    it("renders suggested questions and handles sending chat message", async () => {
      useGraphStore.getState().setChatOpen(true);

      vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
        const url = String(input);
        if (url.includes("/auth/me")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              id: 1,
              github_id: 12345,
              login: "testuser",
              preferred_language: "en",
            }),
          } as Response;
        }
        if (url.includes("/chat")) {
          const stream = new ReadableStream({
            start(controller) {
              const enc = new TextEncoder();
              // Emit step event
              controller.enqueue(
                enc.encode(
                  'data: {"type": "step", "step": 1, "tool": "list_dependencies", "args": {"file": "src/index.ts"}, "duration_ms": 150, "ok": true, "summary": "Found 1 dependency"}\n\n'
                )
              );
              // Emit token event
              controller.enqueue(
                enc.encode('data: {"type": "token", "text": "The main file imports `src/utils.ts`."}\n\n')
              );
              // Emit verification event
              controller.enqueue(
                enc.encode(
                  'data: {"type": "verification", "verified_files": ["src/utils.ts"], "flagged": []}\n\n'
                )
              );
              // Emit done event
              controller.enqueue(enc.encode('data: {"type": "done", "finish_reason": "stop"}\n\n'));
              controller.close();
            },
          });

          return new Response(stream, {
            status: 200,
            headers: { "Content-Type": "text/event-stream" },
          });
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({}),
        } as Response;
      });

      renderWithProviders(<ChatDrawer repoId="repo-123" repoStatus="ready" />);

      // Suggested questions visible
      const starterBtn = await screen.findByText(
        /What are the most depended-on files in this repository\?/i
      );
      expect(starterBtn).toBeInTheDocument();

      // Click starter question
      fireEvent.click(starterBtn);

      // Verify streamed message arrives
      await waitFor(() => {
        expect(
          screen.getByText(/The main file imports/i)
        ).toBeInTheDocument();
        expect(screen.getByText(/Checked imports of src\/index\.ts/i)).toBeInTheDocument();
      });
    });
  });
});
