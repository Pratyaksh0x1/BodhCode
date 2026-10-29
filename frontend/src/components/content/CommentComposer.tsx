import { useState } from "react";
import {
  createCommentPreview,
  editCommentPreview,
  confirmComment,
  type CommentPreviewResponse,
  type SecretDetectedError,
} from "../../lib/push";
import { ApiError } from "../../lib/api";
import { ScopeUpgradeModal } from "../common/ScopeUpgradeModal";

interface CommentComposerProps {
  repoId: number | string;
  issueNumber: number;
  userPreferredLanguage?: string;
  onCommentPosted?: () => void;
}

export function CommentComposer({
  repoId,
  issueNumber,
  userPreferredLanguage = "en",
  onCommentPosted,
}: CommentComposerProps) {
  const [commentBody, setCommentBody] = useState("");
  const [writtenIn, setWrittenIn] = useState(userPreferredLanguage);

  const [preview, setPreview] = useState<CommentPreviewResponse | null>(null);
  const [editedBody, setEditedBody] = useState("");

  const [isLoading, setIsLoading] = useState(false);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [showScopeUpgrade, setShowScopeUpgrade] = useState(false);
  const [postedUrl, setPostedUrl] = useState<string | null>(null);

  const numericRepoId = typeof repoId === "string" ? parseInt(repoId, 10) : repoId;

  const handlePreview = async () => {
    if (!commentBody.trim()) {
      setErrorBanner("Comment text cannot be empty.");
      return;
    }

    setIsLoading(true);
    setErrorBanner(null);
    setPostedUrl(null);

    try {
      const data = await createCommentPreview(numericRepoId, issueNumber, {
        body: commentBody.trim(),
        written_in: writtenIn,
      });

      setPreview(data);
      setEditedBody(data.texts.body.translated);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 403 && err.detail.includes("scope_required")) {
          setShowScopeUpgrade(true);
          return;
        }
        const errBody = err.body as { detail?: SecretDetectedError } | undefined;
        if (errBody?.detail?.error === "secret_detected") {
          setErrorBanner("Blocked: Secrets detected in comment. Please remove before sending.");
          return;
        }
        setErrorBanner(err.detail);
      } else {
        setErrorBanner(err instanceof Error ? err.message : "Failed to create comment preview");
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleConfirm = async () => {
    if (!preview) return;

    setIsLoading(true);
    setErrorBanner(null);

    try {
      if (editedBody !== preview.texts.body.translated) {
        await editCommentPreview(numericRepoId, issueNumber, preview.preview_id, {
          body: editedBody,
        });
      }

      const res = await confirmComment(numericRepoId, issueNumber, preview.preview_id);
      setPostedUrl(res.comment_url);
      setCommentBody("");
      setPreview(null);
      if (onCommentPosted) {
        onCommentPosted();
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 403 && err.detail.includes("scope_required")) {
          setShowScopeUpgrade(true);
          return;
        }
        setErrorBanner(err.detail);
      } else {
        setErrorBanner(err instanceof Error ? err.message : "Failed to submit comment");
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="mt-4 pt-4 border-t border-neutral-800 space-y-3 text-xs">
      <div className="font-semibold text-neutral-200 flex items-center justify-between">
        <span className="flex items-center gap-1.5">
          <span>💬</span>
          <span>Reply to Issue #{issueNumber}</span>
        </span>
        <select
          value={writtenIn}
          onChange={(e) => setWrittenIn(e.target.value)}
          className="px-2 py-0.5 rounded bg-neutral-900 border border-neutral-700 text-[11px] text-neutral-300 focus:outline-none"
        >
          <option value="en">English (en)</option>
          <option value="hi">Hindi (hi)</option>
          <option value="es">Spanish (es)</option>
          <option value="fr">French (fr)</option>
          <option value="de">German (de)</option>
          <option value="ja">Japanese (ja)</option>
          <option value="zh">Chinese (zh)</option>
          <option value="ta">Tamil (ta)</option>
          <option value="te">Telugu (te)</option>
          <option value="bn">Bengali (bn)</option>
        </select>
      </div>

      {errorBanner && (
        <div className="p-2.5 rounded-lg bg-rose-950/40 border border-rose-800/60 text-rose-300 text-[11px] flex items-center justify-between">
          <span>{errorBanner}</span>
          <button
            type="button"
            onClick={() => setErrorBanner(null)}
            className="text-rose-400 hover:text-rose-200 ml-2"
          >
            ✕
          </button>
        </div>
      )}

      {postedUrl && (
        <div className="p-3 rounded-lg bg-emerald-950/40 border border-emerald-800/60 text-emerald-300 text-xs flex items-center justify-between">
          <span>Comment posted successfully!</span>
          <a
            href={postedUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-emerald-400 font-semibold underline hover:text-emerald-300"
          >
            View on GitHub &nearr;
          </a>
        </div>
      )}

      {!preview ? (
        <div className="space-y-2">
          <textarea
            rows={3}
            value={commentBody}
            onChange={(e) => setCommentBody(e.target.value)}
            placeholder="Write a comment in your language..."
            className="w-full px-3 py-2 rounded-xl bg-neutral-950 border border-neutral-800 text-neutral-100 text-xs focus:outline-none focus:border-orange-500 resize-none font-mono"
          />

          <div className="flex justify-end">
            <button
              type="button"
              onClick={handlePreview}
              disabled={isLoading || !commentBody.trim()}
              className="px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-orange-500 hover:bg-orange-600 disabled:opacity-40 disabled:cursor-not-allowed text-white transition-colors cursor-pointer flex items-center gap-1.5"
            >
              {isLoading && (
                <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
              )}
              <span>Preview & Translate &rarr;</span>
            </button>
          </div>
        </div>
      ) : (
        <div className="p-3 rounded-xl bg-neutral-950/60 border border-neutral-800 space-y-3">
          <div className="text-[11px] text-amber-300/90 flex items-center gap-1.5 bg-amber-500/10 p-2 rounded-lg border border-amber-500/20">
            <span>ℹ️</span>
            <span>
              Machine translation into repository language ({preview.repo_language}). Review and edit
              before posting.
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="p-2.5 rounded-lg bg-neutral-900/50 border border-neutral-800">
              <span className="text-[10px] uppercase font-bold text-neutral-400 block pb-1 border-b border-neutral-800">
                Your Comment ({preview.written_in})
              </span>
              <p className="text-neutral-300 text-xs mt-1.5 whitespace-pre-wrap">
                {preview.texts.body.original}
              </p>
            </div>

            <div className="p-2.5 rounded-lg bg-orange-950/20 border border-orange-500/30">
              <span className="text-[10px] uppercase font-bold text-orange-400 block pb-1 border-b border-orange-500/20 flex items-center justify-between">
                <span>Repository Comment ({preview.repo_language})</span>
                <span className="text-[9px] text-neutral-400 font-normal">Editable</span>
              </span>
              <textarea
                rows={3}
                value={editedBody}
                onChange={(e) => setEditedBody(e.target.value)}
                className="w-full mt-1.5 px-2 py-1 rounded bg-neutral-900 border border-neutral-700 text-neutral-100 text-xs focus:outline-none focus:border-orange-500 font-mono resize-none"
              />
            </div>
          </div>

          <div className="flex items-center justify-between pt-1">
            <button
              type="button"
              onClick={() => setPreview(null)}
              disabled={isLoading}
              className="text-xs text-neutral-400 hover:text-neutral-200 cursor-pointer"
            >
              &larr; Cancel / Edit original
            </button>

            <button
              type="button"
              onClick={handleConfirm}
              disabled={isLoading}
              className="px-4 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white transition-colors cursor-pointer flex items-center gap-1.5"
            >
              {isLoading && (
                <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
              )}
              <span>Post Comment</span>
            </button>
          </div>
        </div>
      )}

      <ScopeUpgradeModal
        isOpen={showScopeUpgrade}
        onClose={() => setShowScopeUpgrade(false)}
        neededScope="public_repo"
      />
    </div>
  );
}
