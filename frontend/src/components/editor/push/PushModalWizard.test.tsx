import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { PushModalWizard } from "./PushModalWizard";
import type { ChangedFileItem } from "../../../lib/files";

describe("PushModalWizard", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const mockChanges: ChangedFileItem[] = [
    { path: "src/index.ts", status: "modified", size: 100, language_hint: "typescript" },
    { path: "src/utils.ts", status: "added", size: 50, language_hint: "typescript" },
  ];

  it("renders changed files in review step", () => {
    render(
      <PushModalWizard
        isOpen={true}
        onClose={vi.fn()}
        repoId={1}
        upstreamRepo="facebook/react"
        changes={mockChanges}
      />
    );

    expect(screen.getByText("Push Changes to GitHub")).toBeInTheDocument();
    expect(screen.getByText("src/index.ts")).toBeInTheDocument();
    expect(screen.getByText("src/utils.ts")).toBeInTheDocument();
    expect(screen.getByText("Next: Describe Changes →")).not.toBeDisabled();
  });

  it("blocks next button if sensitive file (.env) is present", () => {
    const sensitiveChanges: ChangedFileItem[] = [
      { path: ".env", status: "modified", size: 20, language_hint: "dotenv" },
      { path: "src/index.ts", status: "modified", size: 100, language_hint: "typescript" },
    ];

    render(
      <PushModalWizard
        isOpen={true}
        onClose={vi.fn()}
        repoId={1}
        upstreamRepo="facebook/react"
        changes={sensitiveChanges}
      />
    );

    expect(
      screen.getByText(/Push Blocked: Secrets or Restricted Files Detected/i)
    ).toBeInTheDocument();
    expect(screen.getByText("Next: Describe Changes →")).toBeDisabled();
  });

  it("advances to compose step on clicking next", () => {
    render(
      <PushModalWizard
        isOpen={true}
        onClose={vi.fn()}
        repoId={1}
        upstreamRepo="facebook/react"
        changes={mockChanges}
      />
    );

    fireEvent.click(screen.getByText("Next: Describe Changes →"));
    expect(screen.getByText("Feature Branch Name")).toBeInTheDocument();
    expect(screen.getByText("Commit Message")).toBeInTheDocument();
  });
});
