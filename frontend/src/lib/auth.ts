import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { api, ApiError } from "./api";

export interface User {
  id: number;
  login: string;
  name: string | null;
  avatar_url: string;
  email: string | null;
  preferred_language: string;
  theme: string;
}

export const AUTH_QUERY_KEY = ["auth", "me"] as const;

export function useMe() {
  return useQuery<User | null, Error>({
    queryKey: AUTH_QUERY_KEY,
    queryFn: async (): Promise<User | null> => {
      try {
        return await api<User>("/auth/me");
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
