import { render, screen, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { RateLimitBanner } from "./RateLimitBanner";
import { useRateLimitStore } from "../../store/rateLimitStore";

describe("RateLimitBanner", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    useRateLimitStore.getState().dismiss();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("does not render when store is inactive", () => {
    const { container } = render(<RateLimitBanner />);
    expect(container.firstChild).toBeNull();
  });

  it("renders when rate limited and counts down", () => {
    act(() => {
      useRateLimitStore.getState().triggerRateLimit(5, "Rate limit reached.");
    });

    render(<RateLimitBanner />);

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Please Slow Down")).toBeInTheDocument();
    expect(screen.getByText("Rate limit reached.")).toBeInTheDocument();
    expect(screen.getByText("5s")).toBeInTheDocument();

    // Fast forward 1 second
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(screen.getByText("4s")).toBeInTheDocument();

    // Fast forward 4 more seconds to reach 0
    act(() => {
      vi.advanceTimersByTime(4000);
    });
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("dismisses immediately when close button is clicked", () => {
    act(() => {
      useRateLimitStore.getState().triggerRateLimit(30);
    });

    render(<RateLimitBanner />);
    expect(screen.getByRole("alert")).toBeInTheDocument();

    const closeBtn = screen.getByLabelText("Dismiss rate limit notice");
    fireEvent.click(closeBtn);

    expect(screen.queryByRole("alert")).toBeNull();
  });
});
