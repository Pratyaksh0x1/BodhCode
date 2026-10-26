import { describe, expect, it } from "vitest";
import { validateRepoUrl } from "./repos";

describe("validateRepoUrl", () => {
  it("accepts clean shorthand owner/repo", () => {
    const res = validateRepoUrl("facebook/react");
    expect(res).toEqual({ owner: "facebook", name: "react" });
  });

  it("strips .git suffix from shorthand", () => {
    const res = validateRepoUrl("facebook/react.git");
    expect(res).toEqual({ owner: "facebook", name: "react" });
  });

  it("accepts full github URL", () => {
    const res = validateRepoUrl("https://github.com/facebook/react");
    expect(res).toEqual({ owner: "facebook", name: "react" });
  });

  it("accepts full github URL with tree subpath", () => {
    const res = validateRepoUrl("https://github.com/facebook/react/tree/main");
    expect(res).toEqual({ owner: "facebook", name: "react" });
  });

  it("throws on empty string", () => {
    expect(() => validateRepoUrl("   ")).toThrow("Repository URL cannot be empty");
  });

  it("throws on non-github host", () => {
    expect(() => validateRepoUrl("https://gitlab.com/owner/repo")).toThrow(
      "Only public GitHub repositories on github.com are supported"
    );
  });

  it("throws on invalid shorthand", () => {
    expect(() => validateRepoUrl("singleword")).toThrow("Invalid format");
  });
});
