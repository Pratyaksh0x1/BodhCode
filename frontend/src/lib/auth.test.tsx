import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, renderHook, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RequireAuth } from "../components/RequireAuth";
import { useLogout, useMe, type User } from "./auth";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/settings"]}>
        <Routes>
          <Route path="/settings" element={children} />
          <Route path="/" element={<div data-testid="home-page">Home Page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("auth and RequireAuth", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("useMe returns user on 200 OK", async () => {
    const mockUser: User = {
      id: 1,
      login: "test-user",
      name: "Test User",
      avatar_url: "https://avatar.url/1.png",
      email: "test@example.com",
      preferred_language: "en",
      theme: "dark",
      editor_theme: "auto",
    };

    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => mockUser,
    } as Response);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(() => useMe(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(mockUser);
  });

  it("useMe returns null when /auth/me responds with 401 Unauthorized", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
      ok: false,
      status: 401,
      statusText: "Unauthorized",
      json: async () => ({ detail: "Not authenticated" }),
    } as Response);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(() => useMe(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toBeNull();
  });

  it("RequireAuth redirects to / when unauthenticated without rendering protected content", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
      ok: false,
      status: 401,
      statusText: "Unauthorized",
      json: async () => ({ detail: "Not authenticated" }),
    } as Response);

    render(
      <RequireAuth>
        <div data-testid="secret-settings">Secret Protected Settings</div>
      </RequireAuth>,
      { wrapper: createWrapper() }
    );

    // Protected content must never be visible
    expect(screen.queryByTestId("secret-settings")).toBeNull();

    // Must navigate to home page
    await waitFor(() => {
      expect(screen.getByTestId("home-page")).toBeDefined();
    });
    expect(screen.queryByTestId("secret-settings")).toBeNull();
  });

  it("useLogout sends POST to /auth/logout", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
      ok: true,
      status: 204,
      json: async () => ({}),
    } as Response);

    const queryClient = new QueryClient();
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(() => useLogout(), { wrapper });
    await result.current();

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining("/auth/logout"),
      expect.objectContaining({
        method: "POST",
      })
    );
  });
});
