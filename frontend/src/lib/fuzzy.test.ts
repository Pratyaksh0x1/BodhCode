import { describe, expect, it } from "vitest";
import { fuzzySearch } from "./fuzzy";

describe("fuzzySearch", () => {
  const files = [
    "src/index.ts",
    "src/components/Button.tsx",
    "src/components/Header.tsx",
    "src/utils/calc.ts",
    "package.json",
    "README.md",
  ];

  it("finds components/Button.tsx with 'compo btn'", () => {
    const results = fuzzySearch("compo btn", files);
    expect(results.length).toBeGreaterThan(0);
    expect(results[0].path).toBe("src/components/Button.tsx");
  });

  it("returns all files when query is empty", () => {
    const results = fuzzySearch("", files);
    expect(results.length).toBe(files.length);
  });

  it("ranks exact filename match above distant match", () => {
    const paths = ["src/lib/button/index.ts", "src/components/Button.tsx"];
    const results = fuzzySearch("Button", paths);
    expect(results[0].path).toBe("src/components/Button.tsx");
  });

  it("returns empty array when no files match", () => {
    const results = fuzzySearch("nonexistentzzxyz", files);
    expect(results.length).toBe(0);
  });
});
