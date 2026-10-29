import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { api, ApiError } from "./api";
import { applyTheme, setStoredTheme, type ThemePref } from "./theme";

export type ReviewMode = "review" | "auto" | "readonly";

export interface User {
  id: number;
  login: string;
  name: string | null;
  avatar_url: string;
  email: string | null;
  preferred_language: string;
  theme: "system" | "light" | "dark" | string;
  editor_theme: "auto" | "vs" | "vs-dark" | "hc-black" | "hc-light" | string;
  review_mode?: ReviewMode;
  grok_configured?: boolean;
  grok_model?: string;
  github_connected?: boolean;
  chatgpt_connected?: boolean;
  openai_model?: string;
  auth_provider?: "github" | "chatgpt" | "both" | string;
}

export const AUTH_QUERY_KEY = ["auth", "me"] as const;

export async function pollDesktopAuthTicket(ticket: string): Promise<User | null> {
  const resp = await api<{ status: string; user?: User }>(`/auth/desktop-poll?ticket=${encodeURIComponent(ticket)}`);
  if (resp.status === "approved" && resp.user) {
    return resp.user;
  }
  return null;
}

export function useChatGPTLogin() {
  const queryClient = useQueryClient();

  return useCallback(
    async (payload: { apiKey: string; model?: string; ticket?: string }): Promise<User> => {
      const resp = await api<{ status: string; user: User }>("/auth/chatgpt/login", {
        method: "POST",
        body: JSON.stringify({
          api_key: payload.apiKey,
          model: payload.model || "gpt-4o",
          ticket: payload.ticket,
        }),
      });

      queryClient.setQueryData(AUTH_QUERY_KEY, resp.user);
      return resp.user;
    },
    [queryClient]
  );
}

export function useMe() {
  return useQuery<User | null, Error>({
    queryKey: AUTH_QUERY_KEY,
    queryFn: async (): Promise<User | null> => {
      try {
        const user = await api<User>("/auth/me");
        if (user?.theme) {
          const themePref = user.theme as ThemePref;
          setStoredTheme(themePref);
          applyTheme(themePref);
        }
        return user;
      } catch (err: unknown) {
        if (err instanceof ApiError && err.status === 401) {
          return null;
        }
        throw err;
      }
    },
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}

export function useLogout() {
  const queryClient = useQueryClient();

  return useCallback(async (): Promise<void> => {
    try {
      await api<void>("/auth/logout", { method: "POST" });
    } finally {
      queryClient.setQueryData(AUTH_QUERY_KEY, null);
      queryClient.clear();
    }
  }, [queryClient]);
}

export function useDisconnect() {
  const queryClient = useQueryClient();

  return useCallback(async (): Promise<void> => {
    try {
      await api<void>("/auth/disconnect", { method: "POST" });
    } finally {
      queryClient.setQueryData(AUTH_QUERY_KEY, null);
      queryClient.clear();
      window.location.href = "/";
    }
  }, [queryClient]);
}
