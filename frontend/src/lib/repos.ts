import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";

export interface Repo {
  id: number;
  user_id: number;
  owner: string;
  name: string;
  branch: string;
  commit_sha: string | null;
  default_branch_size_kb: number | null;
  file_count: number | null;
  status: "queued" | "fetching" | "fetched" | "analyzing" | "ready" | "failed";
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface GraphStats {
  files: number;
  edges: number;
  external_packages: number;
  cycles: number;
  unresolved: number;
}

export interface GraphNode {
  id: string;
  name: string;
  folder: string;
  size: number;
  exports: string[];
  has_default_export: boolean;
  external_deps: string[];
  unresolved_count: number;
  unresolved_dynamic: number;
  flags: string[];
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  kind: string;
  type_only: boolean;
  count: number;
}

export interface GraphFolder {
  id: string;
  parent: string;
  file_count: number;
}

export interface GraphDoc {
  version: number;
  repo: {
    owner: string;
    name: string;
    commit_sha: string;
  };
  nodes: GraphNode[];
  edges: GraphEdge[];
  folders: GraphFolder[];
  stats: GraphStats;
}

export interface BlastImpact {
  file: string;
  depth: number;
  via: string;
}

export interface BlastResult {
  file: string;
  total: number;
  impacts: BlastImpact[];
}

export interface FileDepsResult {
  file: string;
  dependencies: string[];
  dependents: string[];
}

const GITHUB_NAME_REGEX = /^[a-zA-Z0-9_.-]+$/;

export function validateRepoUrl(input: string): { owner: string; name: string } {
  const trimmed = input.trim();
  if (!trimmed) {
    throw new Error("Repository URL cannot be empty.");
  }

  // Shorthand format: owner/repo
  if (!trimmed.includes("://") && !trimmed.startsWith("www.") && !trimmed.startsWith("github.com")) {
    const parts = trimmed.split("/").filter(Boolean);
    if (parts.length === 2) {
      const owner = parts[0];
      let name = parts[1];
      if (name.endsWith(".git")) {
        name = name.slice(0, -4);
      }
      if (!GITHUB_NAME_REGEX.test(owner) || !GITHUB_NAME_REGEX.test(name)) {
        throw new Error("Repository owner and name must contain only alphanumeric characters, hyphens, periods, or underscores.");
      }
      return { owner, name };
    }
    throw new Error("Invalid format. Use 'owner/repo' or full GitHub URL (e.g. 'https://github.com/facebook/react').");
  }

  // Full URL
  const normalized = trimmed.startsWith("http://") || trimmed.startsWith("https://")
    ? trimmed
    : `https://${trimmed}`;

  try {
    const url = new URL(normalized);
    const host = url.hostname.toLowerCase();
    if (host !== "github.com" && host !== "www.github.com") {
      throw new Error(`Only public GitHub repositories on github.com are supported. Received '${url.hostname}'.`);
    }

    const segments = url.pathname.split("/").filter(Boolean);
    if (segments.length < 2) {
      throw new Error("GitHub URL must contain both an owner and a repository name.");
    }

    const owner = segments[0];
    let name = segments[1];
    if (name.endsWith(".git")) {
      name = name.slice(0, -4);
    }

    if (!GITHUB_NAME_REGEX.test(owner) || !GITHUB_NAME_REGEX.test(name)) {
      throw new Error("Repository owner and name must contain only alphanumeric characters, hyphens, periods, or underscores.");
    }

    return { owner, name };
  } catch (err: unknown) {
    if (err instanceof Error) {
      throw err;
    }
    throw new Error("Invalid GitHub repository URL.", { cause: err });
  }
}

export const REPOS_QUERY_KEY = ["repos"] as const;

export function useRepos() {
  return useQuery<Repo[], Error>({
    queryKey: REPOS_QUERY_KEY,
    queryFn: () => api<Repo[]>("/repos"),
    refetchInterval: (query) => {
      const data = query.state.data;
      if (
        data &&
        data.some(
          (r) => r.status === "queued" || r.status === "fetching" || r.status === "analyzing"
        )
      ) {
        return 1500;
      }
      return false;
    },
  });
}

export function useRepo(id: number | string | undefined) {
  return useQuery<Repo, Error>({
    queryKey: [...REPOS_QUERY_KEY, id],
    queryFn: () => api<Repo>(`/repos/${id}`),
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const data = query.state.data;
      if (
        data &&
        (data.status === "queued" || data.status === "fetching" || data.status === "analyzing")
      ) {
        return 1500;
      }
      return false;
    },
  });
}

export function useAnalyzeRepo() {
  const queryClient = useQueryClient();

  return useMutation<Repo, Error, number>({
    mutationFn: (id: number) =>
      api<Repo>(`/repos/${id}/analyze`, {
        method: "POST",
      }),
    onSuccess: (data) => {
      queryClient.setQueryData([...REPOS_QUERY_KEY, String(data.id)], data);
      queryClient.invalidateQueries({ queryKey: REPOS_QUERY_KEY });
    },
  });
}

export function useRepoGraph(id: number | string | undefined, enabled: boolean = true) {
  return useQuery<GraphDoc, Error>({
    queryKey: ["repo_graph", id],
    queryFn: () => api<GraphDoc>(`/repos/${id}/graph`),
    enabled: Boolean(id) && enabled,
    staleTime: 60_000,
  });
}

export function useCreateRepo() {
  const queryClient = useQueryClient();

  return useMutation<Repo, Error, string>({
    mutationFn: (url: string) =>
      api<Repo>("/repos", {
        method: "POST",
        body: JSON.stringify({ url }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: REPOS_QUERY_KEY });
    },
  });
}

export function useRefreshRepo() {
  const queryClient = useQueryClient();

  return useMutation<Repo, Error, number>({
    mutationFn: (id: number) =>
      api<Repo>(`/repos/${id}/refresh`, {
        method: "POST",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: REPOS_QUERY_KEY });
    },
  });
}

export function useDeleteRepo() {
  const queryClient = useQueryClient();

  return useMutation<void, Error, number>({
    mutationFn: (id: number) =>
      api<void>(`/repos/${id}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: REPOS_QUERY_KEY });
    },
  });
}

export function useFileDeps(
  repoId: number | string | undefined,
  file: string | null,
  enabled: boolean = true
) {
  return useQuery<FileDepsResult, Error>({
    queryKey: ["repo_deps", repoId, file],
    queryFn: () =>
      api<FileDepsResult>(
        `/repos/${repoId}/deps?file=${encodeURIComponent(file || "")}&depth=1`
      ),
    enabled: Boolean(repoId && file) && enabled,
    staleTime: 60_000,
  });
}

export function useFileBlastMutation(repoId: number | string | undefined) {
  return useMutation<BlastResult, Error, { file: string; includeTypeOnly?: boolean }>({
    mutationFn: ({ file, includeTypeOnly = true }) =>
      api<BlastResult>(
        `/repos/${repoId}/blast?file=${encodeURIComponent(file)}&include_type_only=${includeTypeOnly}`
      ),
  });
}

