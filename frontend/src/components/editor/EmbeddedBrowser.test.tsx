import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EmbeddedBrowser } from "./EmbeddedBrowser";

describe("EmbeddedBrowser Component", () => {
  it("renders address bar, default URL, and Go button", () => {
    render(<EmbeddedBrowser initialUrl="http://localhost:5173" />);
    expect(screen.getByText("Embedded Local Browser")).toBeDefined();
    const input = screen.getByPlaceholderText("http://localhost:5173") as HTMLInputElement;
    expect(input.value).toBe("http://localhost:5173");
    expect(screen.getByText("Go")).toBeDefined();
  });

  it("updates URL and triggers screenshot feedback", () => {
    render(<EmbeddedBrowser initialUrl="http://localhost:5173" />);
    const screenshotBtn = screen.getByText("Screenshot");
    fireEvent.click(screenshotBtn);
    expect(screen.getByText(/Viewport snapshot captured/i)).toBeDefined();
  });

  it("toggles DOM Inspector preview panel", () => {
    render(<EmbeddedBrowser initialUrl="http://localhost:5173" />);
    const inspectorBtn = screen.getByText("Inspector");
    fireEvent.click(inspectorBtn);
    expect(screen.getByText("DOM Element Inspector")).toBeDefined();
    fireEvent.click(inspectorBtn);
    expect(screen.queryByText("DOM Element Inspector")).toBeNull();
  });
});
