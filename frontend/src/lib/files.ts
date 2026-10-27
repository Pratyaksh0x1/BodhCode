/**
 * API client and React Query hooks for working files, editor workspace, and diffs.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";

export type FileStatus = "unchanged" | "modified" | "added" | "deleted";

export interface RepoFileItem {
  path: string;
  status: FileStatus;
  graph_node: boolean;
  size: number;
}

export interface FileTreeResponse {
  files: RepoFileItem[];
  count: number;
}

export interface FileContentResponse {
  path: string;
  content: string;
  language_hint: string;
  status: FileStatus;
  size: number;
  hash: string;
  content_hash: string;
  base_hash: string | null;
}

export interface WriteFileResult {
  path: string;
  status: FileStatus;
  hash: string;
  content_hash: string;
  size: number;
}

export interface ChangedFileItem {
  path: string;
  status: FileStatus;
  size: number;
  language_hint: string;
}

export interface RepoChangesResponse {
  changes: ChangedFileItem[];
  count: number;
}

export interface FileDiffResponse {
  path: string;
  status: FileStatus;
  original: string;
  modified: string;
}

export async function fetchRepoFiles(repoId: string | number): Promise<FileTreeResponse> {
  return api<FileTreeResponse>(`/repos/${repoId}/files`);
}

export async function fetchFileContent(
  repoId: string | number,
  path: string
): Promise<FileContentResponse> {
  return api<FileContentResponse>(`/repos/${repoId}/files/${encodeURIComponent(path)}`);
}

export async function saveRepoFile(
  repoId: string | number,
  path: string,
  content: string,
  ifMatch?: string | null
): Promise<WriteFileResult> {
  const headers: Record<string, string> = {};
  if (ifMatch) {
    headers["If-Match"] = `"${ifMatch.replace(/^"|"$/g, "")}"`;
  }
  return api<WriteFileResult>(`/repos/${repoId}/files/${encodeURIComponent(path)}`, {
    method: "PUT",
    body: JSON.stringify({ content }),
    headers,
  });
}

export async function deleteRepoFile(
  repoId: string | number,
  path: string
): Promise<{ path: string; status: FileStatus }> {
  return api<{ path: string; status: FileStatus }>(
    `/repos/${repoId}/files/${encodeURIComponent(path)}`,
    {
      method: "DELETE",
    }
  );
}

export async function revertRepoFile(
  repoId: string | number,
  path: string
): Promise<{ path: string; reverted: boolean }> {
  return api<{ path: string; reverted: boolean }>(
    `/repos/${repoId}/files/${encodeURIComponent(path)}/revert`,
    {
      method: "POST",
    }
  );
}

export async function fetchRepoChanges(
  repoId: string | number
): Promise<RepoChangesResponse> {
  return api<RepoChangesResponse>(`/repos/${repoId}/changes`);
}

export async function fetchFileDiff(
  repoId: string | number,
  path: string
): Promise<FileDiffResponse> {
  return api<FileDiffResponse>(`/repos/${repoId}/diff/${encodeURIComponent(path)}`);
}

export async function renameRepoFile(
  repoId: string | number,
  oldPath: string,
  newPath: string
): Promise<{ old_path: string; new_path: string; status: string }> {
  return api<{ old_path: string; new_path: string; status: string }>(
    `/repos/${repoId}/files/${encodeURIComponent(oldPath)}/rename`,
    {
      method: "POST",
      body: JSON.stringify({ new_path: newPath }),
    }
  );
}

export function useRepoFiles(repoId: string | number | undefined) {
  return useQuery({
    queryKey: ["repo-files", repoId],
    queryFn: () => (repoId ? fetchRepoFiles(repoId) : Promise.reject(new Error("No repo ID"))),
    enabled: Boolean(repoId),
  });
}

export function useFileContent(
  repoId: string | number | undefined,
  filePath: string | null
) {
  return useQuery({
    queryKey: ["repo-file-content", repoId, filePath],
    queryFn: () =>
      repoId && filePath
        ? fetchFileContent(repoId, filePath)
        : Promise.reject(new Error("Missing repo ID or file path")),
    enabled: Boolean(repoId && filePath),
  });
}

export function useRepoChanges(repoId: string | number | undefined) {
  return useQuery({
    queryKey: ["repo-changes", repoId],
    queryFn: () =>
      repoId ? fetchRepoChanges(repoId) : Promise.reject(new Error("No repo ID")),
    enabled: Boolean(repoId),
  });
}

export function useFileDiff(
  repoId: string | number | undefined,
  filePath: string | null
) {
  return useQuery({
    queryKey: ["repo-file-diff", repoId, filePath],
    queryFn: () =>
      repoId && filePath
        ? fetchFileDiff(repoId, filePath)
        : Promise.reject(new Error("Missing repo ID or file path")),
    enabled: Boolean(repoId && filePath),
  });
}

export function useSaveFile(repoId: string | number | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      path,
      content,
      ifMatch,
    }: {
      path: string;
      content: string;
      ifMatch?: string | null;
    }) => {
      if (!repoId) throw new Error("Missing repo ID");
      return saveRepoFile(repoId, path, content, ifMatch);
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["repo-files", repoId] });
      queryClient.invalidateQueries({ queryKey: ["repo-changes", repoId] });
      queryClient.invalidateQueries({
        queryKey: ["repo-file-content", repoId, variables.path],
      });
      queryClient.invalidateQueries({
        queryKey: ["repo-file-diff", repoId, variables.path],
      });
    },
  });
}

export function useDeleteFile(repoId: string | number | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (path: string) => {
      if (!repoId) throw new Error("Missing repo ID");
      return deleteRepoFile(repoId, path);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["repo-files", repoId] });
      queryClient.invalidateQueries({ queryKey: ["repo-changes", repoId] });
    },
  });
}

export function useRevertFile(repoId: string | number | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (path: string) => {
      if (!repoId) throw new Error("Missing repo ID");
      return revertRepoFile(repoId, path);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["repo-files", repoId] });
      queryClient.invalidateQueries({ queryKey: ["repo-changes", repoId] });
    },
  });
}

export function useRenameFile(repoId: string | number | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ oldPath, newPath }: { oldPath: string; newPath: string }) => {
      if (!repoId) throw new Error("Missing repo ID");
      return renameRepoFile(repoId, oldPath, newPath);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["repo-files", repoId] });
      queryClient.invalidateQueries({ queryKey: ["repo-changes", repoId] });
    },
  });
}
