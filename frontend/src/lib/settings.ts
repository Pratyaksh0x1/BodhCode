import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import { AUTH_QUERY_KEY, useMe, type ReviewMode, type User } from "./auth";
import { applyTheme, setStoredTheme, type EditorThemePref, type ThemePref } from "./theme";

export interface Language {
  code: string;
  english_name: string;
  native_name: string;
  rtl: boolean;
}

export interface UserSettingsPayload {
  preferred_language?: string;
  theme?: ThemePref;
  editor_theme?: EditorThemePref;
  review_mode?: ReviewMode;
  grok_api_key?: string;
  grok_model?: string;
}

export const LANGUAGES_QUERY_KEY = ["meta", "languages"] as const;

export function useLanguages() {
  return useQuery<Language[], Error>({
    queryKey: LANGUAGES_QUERY_KEY,
    queryFn: () => api<Language[]>("/meta/languages"),
    staleTime: 24 * 60 * 60 * 1000,
  });
}

export function useSettings() {
  const queryClient = useQueryClient();
  const { data: user, isLoading, error: userError } = useMe();

  const updateMutation = useMutation<
    User,
    Error,
    UserSettingsPayload,
    { previousUser: User | null | undefined }
  >({
    mutationFn: (settings: UserSettingsPayload) =>
      api<User>("/auth/me/settings", {
        method: "PATCH",
        body: JSON.stringify(settings),
      }),
    onMutate: async (newSettings) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: AUTH_QUERY_KEY });

      // Snapshot previous value
      const previousUser = queryClient.getQueryData<User | null>(AUTH_QUERY_KEY);

      // Optimistically update query data
      if (previousUser) {
        queryClient.setQueryData<User>(AUTH_QUERY_KEY, {
          ...previousUser,
          ...newSettings,
        });
      }

      // Optimistically apply theme immediately
      if (newSettings.theme) {
        setStoredTheme(newSettings.theme);
        applyTheme(newSettings.theme);
      }

      return { previousUser };
    },
    onError: (_err, _newSettings, context) => {
      // Rollback on error
      if (context?.previousUser !== undefined) {
        queryClient.setQueryData(AUTH_QUERY_KEY, context.previousUser);
        if (context.previousUser?.theme) {
          const revertTheme = context.previousUser.theme as ThemePref;
          setStoredTheme(revertTheme);
          applyTheme(revertTheme);
        }
      }
    },
    onSuccess: (updatedUser) => {
      queryClient.setQueryData(AUTH_QUERY_KEY, updatedUser);
      if (updatedUser.theme) {
        const serverTheme = updatedUser.theme as ThemePref;
        setStoredTheme(serverTheme);
        applyTheme(serverTheme);
      }
    },
  });

  return {
    user,
    isLoading,
    userError,
    updateSettings: updateMutation.mutate,
    updateSettingsAsync: updateMutation.mutateAsync,
    isUpdating: updateMutation.isPending,
    isSuccess: updateMutation.isSuccess,
    error: updateMutation.error,
    reset: updateMutation.reset,
  };
}
