import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MultilingualViewer } from "./MultilingualViewer";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false },
  },
});

describe("MultilingualViewer Component", () => {
  it("renders tabs, title, and language selector", () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MultilingualViewer repoId="1" />
      </QueryClientProvider>
    );

    expect(screen.getByText("Multilingual Repo Reader")).toBeDefined();
    expect(screen.getByText("README")).toBeDefined();
    expect(screen.getByText("Issues")).toBeDefined();
    expect(screen.getByText("PRs")).toBeDefined();
  });

  it("switches to Issues and PRs tabs", () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MultilingualViewer repoId="1" />
      </QueryClientProvider>
    );

    const issuesTab = screen.getByText("Issues");
    fireEvent.click(issuesTab);
    expect(screen.getByText(/Memory leak during large tree AST parsing/i)).toBeDefined();

    const prsTab = screen.getByText("PRs");
    fireEvent.click(prsTab);
    expect(screen.getByText(/Grok 120B model support/i)).toBeDefined();
  });
});
