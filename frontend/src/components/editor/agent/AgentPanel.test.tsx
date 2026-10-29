import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AgentPanel, type PendingSelection } from "./AgentPanel";
import { ToolStepRow } from "./ToolStepRow";
import { AcceptAllBar } from "./AcceptAllBar";
import type { ToolStep } from "../../../lib/agent";

// Mock Monaco DiffEditor
vi.mock("@monaco-editor/react", () => ({
  DiffEditor: () => <div data-testid="mock-diff-editor" />,
}));

// Mock API calls
vi.mock("../../../lib/api", () => ({
  api: vi.fn(async (path: string) => {
    if (path.includes("/proposals")) {
      return [
        {
          id: 101,
          user_id: 1,
          repo_id: 1,
          session_id: null,
          kind: "edit",
          path: "src/app.ts",
          old_content: "const a = 1;",
          new_content: "const a = 2;",
          base_hash: "hash123",
          rationale: "Increment a",
          blast_radius_count: 3,
          status: "pending",
          is_stale: false,
          created_at: new Date().toISOString(),
          decided_at: null,
        },
        {
          id: 102,
          user_id: 1,
          repo_id: 1,
          session_id: null,
          kind: "create",
          path: "src/util.ts",
          old_content: null,
          new_content: "export const ok = true;",
          base_hash: null,
          rationale: "Add util",
          blast_radius_count: 0,
          status: "pending",
          is_stale: false,
          created_at: new Date().toISOString(),
          decided_at: null,
        },
      ];
    }
    return {};
  }),
}));

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("Coding Agent Frontend Components", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders ToolStepRow with status indicator and expands arguments", () => {
    const step: ToolStep = {
      step: 1,
      tool: "read_file",
      args: { path: "src/index.ts", start: 1, end: 50 },
      duration_ms: 42,
      ok: true,
      summary: "read_file src/index.ts (ok)",
    };

    render(<ToolStepRow step={step} />);

    expect(screen.getByText("read_file")).toBeInTheDocument();
    expect(screen.getByText("read_file src/index.ts (ok)")).toBeInTheDocument();
    expect(screen.getByText("42ms")).toBeInTheDocument();

    // Toggle expand
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText(/"path": "src\/index.ts"/)).toBeInTheDocument();
  });

  it("renders AcceptAllBar when 2 or more proposals are pending", () => {
    renderWithClient(
      <AcceptAllBar repoId={1} pendingCount={2} onBatchDecided={vi.fn()} />
    );

    expect(screen.getByText(/2/)).toBeInTheDocument();
    expect(screen.getByText(/proposals pending review/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Accept All" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reject All" })).toBeInTheDocument();
  });

  it("renders AgentPanel with review mode selector and selection chip", () => {
    const clearMock = vi.fn();
    const sel: PendingSelection = {
      path: "src/index.ts",
      start_line: 10,
      end_line: 20,
      text: "const x = 1;",
      action: "edit",
    };

    renderWithClient(
      <AgentPanel
        repoId={1}
        activeFilePath="src/index.ts"
        pendingSelection={sel}
        onClearSelection={clearMock}
        onOpenFile={vi.fn()}
        theme="vs-dark"
      />
    );

    expect(screen.getByText("BodhCode Agent")).toBeInTheDocument();
    expect(screen.getAllByRole("combobox")[1]).toHaveValue("review");
    expect(screen.getByText(/Changes become proposal diffs/)).toBeInTheDocument();

    // Selection chip
    expect(screen.getByText(/src\/index.ts:10-20/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("✕"));
    expect(clearMock).toHaveBeenCalled();
  });
});
