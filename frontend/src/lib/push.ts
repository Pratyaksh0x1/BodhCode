import { api } from "./api";

export interface SecretFinding {
  path: string;
  rule_name: string;
}

export interface SecretDetectedError {
  error: "secret_detected";
  message: string;
  findings: SecretFinding[];
}

export interface ScopeRequiredErrorDetail {
  detail: "scope_required";
  needed: string;
}

export interface WorkingCopyChangeItem {
  path: string;
  status: "modified" | "added" | "deleted";
  content_hash: string;
}

export interface TranslationTextPair {
  original: string;
  translated: string;
  language: string;
}

export interface PushPreviewRequest {
  branch_name: string;
  commit_message: string;
  pr_title: string;
  pr_body?: string;
  language_override?: string;
}

export interface PushPreviewResponse {
  preview_id: string;
  upstream_repo: string;
  target_repo: string;
  will_fork: boolean;
  base_branch: string;
  head_branch: string;
  repo_language: string;
  written_in: string;
  changes: WorkingCopyChangeItem[];
  working_copy_hash: string;
  texts: {
    commit_message: TranslationTextPair;
    pr_title: TranslationTextPair;
    pr_body: TranslationTextPair;
  };
  expires_at: string;
}

export interface PushPreviewEditRequest {
  branch_name?: string;
  commit_message?: string;
  pr_title?: string;
  pr_body?: string;
}

export interface PushConfirmResponse {
  pr_url: string;
  branch_name: string;
  commit_sha: string;
  fork_url?: string;
}

export interface IssuePreviewRequest {
  title: string;
  body: string;
  written_in?: string;
}

export interface IssuePreviewResponse {
  preview_id: string;
  repo_language: string;
  written_in: string;
  texts: {
    title: TranslationTextPair;
    body: TranslationTextPair;
  };
  expires_at: string;
}

export interface IssuePreviewEditRequest {
  title?: string;
  body?: string;
}

export interface IssueConfirmResponse {
  issue_url: string;
  number: number;
}

export interface CommentPreviewRequest {
  body: string;
  written_in?: string;
}

export interface CommentPreviewResponse {
  preview_id: string;
  repo_language: string;
  written_in: string;
  texts: {
    body: TranslationTextPair;
  };
  expires_at: string;
}

export interface CommentPreviewEditRequest {
  body?: string;
}

export interface CommentConfirmResponse {
  comment_url: string;
}

export interface UserActivityItem {
  id: number;
  repo_id: number | null;
  action: string;
  status: string;
  target_url: string | null;
  created_at: string;
  meta: Record<string, unknown>;
}

export async function createPushPreview(
  repoId: number,
  req: PushPreviewRequest
): Promise<PushPreviewResponse> {
  return api<PushPreviewResponse>(`/repos/${repoId}/push/preview`, {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function editPushPreview(
  repoId: number,
  previewId: string,
  req: PushPreviewEditRequest
): Promise<PushPreviewResponse> {
  return api<PushPreviewResponse>(`/repos/${repoId}/push/preview/${previewId}/edit`, {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function confirmPush(
  repoId: number,
  previewId: string
): Promise<PushConfirmResponse> {
  return api<PushConfirmResponse>(`/repos/${repoId}/push`, {
    method: "POST",
    body: JSON.stringify({ preview_id: previewId, confirm: true }),
  });
}

export async function updateRepoPushLanguage(
  repoId: number,
  language: string | null
): Promise<{ push_language_override: string | null }> {
  return api<{ push_language_override: string | null }>(`/repos/${repoId}/language`, {
    method: "PATCH",
    body: JSON.stringify({ push_language_override: language }),
  });
}

export async function createIssuePreview(
  repoId: number,
  req: IssuePreviewRequest
): Promise<IssuePreviewResponse> {
  return api<IssuePreviewResponse>(`/repos/${repoId}/issues/preview`, {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function editIssuePreview(
  repoId: number,
  previewId: string,
  req: IssuePreviewEditRequest
): Promise<IssuePreviewResponse> {
  return api<IssuePreviewResponse>(`/repos/${repoId}/issues/preview/${previewId}/edit`, {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function confirmIssue(
  repoId: number,
  previewId: string
): Promise<IssueConfirmResponse> {
  return api<IssueConfirmResponse>(`/repos/${repoId}/issues`, {
    method: "POST",
    body: JSON.stringify({ preview_id: previewId, confirm: true }),
  });
}

export async function createCommentPreview(
  repoId: number,
  issueNumber: number,
  req: CommentPreviewRequest
): Promise<CommentPreviewResponse> {
  return api<CommentPreviewResponse>(`/repos/${repoId}/issues/${issueNumber}/comments/preview`, {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function editCommentPreview(
  repoId: number,
  issueNumber: number,
  previewId: string,
  req: CommentPreviewEditRequest
): Promise<CommentPreviewResponse> {
  return api<CommentPreviewResponse>(
    `/repos/${repoId}/issues/${issueNumber}/comments/preview/${previewId}/edit`,
    {
      method: "POST",
      body: JSON.stringify(req),
    }
  );
}

export async function confirmComment(
  repoId: number,
  issueNumber: number,
  previewId: string
): Promise<CommentConfirmResponse> {
  return api<CommentConfirmResponse>(`/repos/${repoId}/issues/${issueNumber}/comments`, {
    method: "POST",
    body: JSON.stringify({ preview_id: previewId, confirm: true }),
  });
}

export async function getUserActivity(limit = 50): Promise<UserActivityItem[]> {
  return api<UserActivityItem[]>(`/user/activity?limit=${limit}`);
}
