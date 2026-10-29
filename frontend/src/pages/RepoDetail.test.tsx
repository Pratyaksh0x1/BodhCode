import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RepoDetail } from "./RepoDetail";

// Mock resize observer for React Flow
globalThis.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

vi.mock("../lib/auth", () => ({
  useMe: () => ({ data: { id: 1, login: "test", preferred_language: "en" }, isLoading: false }),
}));

vi.mock("../lib/repos", () => ({
  useRepo: () => ({
    data: {
      id: 1,
      owner: "Pratyaksh0x1",
      name: "ClawNest",
      branch: "main",
      status: "ready",
      commit_sha: "ee7555e",
    },
    isLoading: false,
    isError: false,
  }),
  useAnalyzeRepo: () => ({ mutate: vi.fn(), isPending: false }),
  useRepoGraph: () => ({
    data: {
      nodes: [
        { id: "src/index.ts", name: "index.ts", folder: "src", size: 100, exports: [], has_default_export: false, external_deps: [], unresolved_count: 0, unresolved_dynamic: 0, flags: [] }
      ],
      edges: [],
      stats: { files: 1, edges: 0, external_packages: 0, cycles: 0, unresolved: 0 }
    },
    isLoading: false,
  }),
}));

describe("RepoDetail page", () => {
  it("renders without crashing", () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/repos/1"]}>
          <Routes>
            <Route path="/repos/:id" element={<RepoDetail />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(screen.getAllByText("ClawNest").length).toBeGreaterThan(0);
    expect(screen.getByText("Ask AI Chat")).toBeDefined();
  });
});
