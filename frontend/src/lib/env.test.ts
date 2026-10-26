import { describe, it, expect } from "vitest";
import { VITE_API_URL } from "./env";

describe("env helper", () => {
  it("exports a non-empty normalized VITE_API_URL without trailing slash", () => {
    expect(typeof VITE_API_URL).toBe("string");
    expect(VITE_API_URL.length).toBeGreaterThan(0);
    expect(VITE_API_URL.endsWith("/")).toBe(false);
  });

  it("throws a clear error if VITE_API_URL is missing or empty", () => {
    const validateEnv = (val: unknown) => {
      if (!val || typeof val !== "string" || !val.trim()) {
        throw new Error(
          "Missing required environment variable: VITE_API_URL. Please set VITE_API_URL in frontend/.env"
        );
      }
      return val.trim().replace(/\/+$/, "");
    };

    expect(() => validateEnv("")).toThrow("Missing required environment variable: VITE_API_URL");
    expect(() => validateEnv(undefined)).toThrow("Missing required environment variable: VITE_API_URL");
  });
});
