import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ScopeUpgradeModal } from "./ScopeUpgradeModal";

describe("ScopeUpgradeModal", () => {
  it("renders modal with explanation and upgrade link", () => {
    const handleClose = vi.fn();
    render(
      <ScopeUpgradeModal
        isOpen={true}
        onClose={handleClose}
        neededScope="public_repo"
        returnTo="/repos/1"
      />
    );

    expect(screen.getByText("GitHub Permission Required")).toBeInTheDocument();
    expect(screen.getAllByText("public_repo").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Why BodhCode requests this permission/i)).toBeInTheDocument();

    const upgradeLink = screen.getByText("Upgrade GitHub Permissions");
    expect(upgradeLink.closest("a")).toHaveAttribute(
      "href",
      expect.stringContaining("/auth/github/upgrade?return_to=")
    );

    const cancelBtn = screen.getByText("Cancel");
    fireEvent.click(cancelBtn);
    expect(handleClose).toHaveBeenCalledOnce();
  });

  it("does not render when isOpen is false", () => {
    const { container } = render(
      <ScopeUpgradeModal isOpen={false} onClose={vi.fn()} />
    );
    expect(container.firstChild).toBeNull();
  });
});
