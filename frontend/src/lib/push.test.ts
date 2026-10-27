import { describe, it, expect, beforeEach, vi } from "vitest";
import {
  createPushPreview,
  editPushPreview,
  confirmPush,
  updateRepoPushLanguage,
  createIssuePreview,
  editIssuePreview,
  confirmIssue,
  createCommentPreview,
  editCommentPreview,
  confirmComment,
  getUserActivity,
} from "./push";

describe("push API client", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("calls createPushPreview with POST and payload", async () => {
    const mockResp = { preview_id: "prev-123" };
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => mockResp,
    } as Response);

    const result = await createPushPreview(1, {
      branch_name: "feat/foo",
      commit_message: "Add foo",
      pr_title: "Add foo",
    });

    expect(result).toEqual(mockResp);
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining("/repos/1/push/preview"),
      expect.objectContaining({
        method: "POST",
      })
    );
  });

  it("calls editPushPreview with edited fields", async () => {
    const mockResp = { preview_id: "prev-123" };
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => mockResp,
    } as Response);

    const result = await editPushPreview(1, "prev-123", {
      commit_message: "Edited commit",
    });
    expect(result).toEqual(mockResp);
  });

  it("calls confirmPush with confirm flag", async () => {
    const mockResp = { pr_url: "https://github.com/pull/1" };
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => mockResp,
    } as Response);

    const result = await confirmPush(1, "prev-123");
    expect(result).toEqual(mockResp);
  });

  it("calls updateRepoPushLanguage with PATCH", async () => {
    const mockResp = { push_language_override: "hi" };
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => mockResp,
    } as Response);

    const result = await updateRepoPushLanguage(1, "hi");
    expect(result).toEqual(mockResp);
  });

  it("calls createIssuePreview, editIssuePreview, confirmIssue", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ preview_id: "iss-1" }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ preview_id: "iss-1" }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ issue_url: "https://github.com/issues/1", number: 1 }),
      } as Response);

    const prev = await createIssuePreview(1, { title: "Title", body: "Body" });
    expect(prev.preview_id).toBe("iss-1");

    const edit = await editIssuePreview(1, "iss-1", { title: "Title edited" });
    expect(edit.preview_id).toBe("iss-1");

    const conf = await confirmIssue(1, "iss-1");
    expect(conf.number).toBe(1);
  });

  it("calls createCommentPreview, editCommentPreview, confirmComment", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ preview_id: "comm-1" }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ preview_id: "comm-1" }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ comment_url: "https://github.com/issues/1#issuecomment-1" }),
      } as Response);

    const prev = await createCommentPreview(1, 10, { body: "Comment" });
    expect(prev.preview_id).toBe("comm-1");

    const edit = await editCommentPreview(1, 10, "comm-1", { body: "Edited comment" });
    expect(edit.preview_id).toBe("comm-1");

    const conf = await confirmComment(1, 10, "comm-1");
    expect(conf.comment_url).toContain("issuecomment-1");
  });

  it("calls getUserActivity with GET", async () => {
    const mockLogs = [{ id: 1, action: "push", status: "succeeded" }];
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => mockLogs,
    } as Response);

    const logs = await getUserActivity(20);
    expect(logs).toEqual(mockLogs);
  });
});
