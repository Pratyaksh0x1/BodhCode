import { describe, it, expect, beforeEach, vi } from "vitest";
import { api, ApiError } from "./api";
import { VITE_API_URL } from "./env";

describe("api helper", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("prefixes VITE_API_URL and sends credentials include on GET", async () => {
    const mockData = { status: "ok" };
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => mockData,
    } as Response);

    const result = await api<{ status: string }>("/health");
    expect(result).toEqual(mockData);
    expect(fetchSpy).toHaveBeenCalledWith(
      `${VITE_API_URL}/health`,
      expect.objectContaining({
        method: "GET",
        credentials: "include",
      })
    );
  });

  it("adds X-Requested-With and Content-Type for POST requests with body", async () => {
    const payload = { query: "test" };
    const mockData = { id: 1 };
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => mockData,
    } as Response);

    await api("/data", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    const callArgs = fetchSpy.mock.calls[0];
    const headers = callArgs[1]?.headers as Headers;
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(headers.get("X-Requested-With")).toBe("bodhcode");
  });

  it("throws typed ApiError with status and detail on non-2xx responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      status: 404,
      statusText: "Not Found",
      json: async () => ({ detail: "Repository not found" }),
    } as Response);

    await expect(api("/repos/nonexistent")).rejects.toThrow(ApiError);

    try {
      await api("/repos/nonexistent");
    } catch (err) {
      if (err instanceof ApiError) {
        expect(err.status).toBe(404);
        expect(err.detail).toBe("Repository not found");
      }
    }
  });
});
