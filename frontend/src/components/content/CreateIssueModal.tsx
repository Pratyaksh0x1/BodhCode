import { useState } from "react";
import {
  createIssuePreview,
  editIssuePreview,
  confirmIssue,
  type IssuePreviewResponse,
  type SecretDetectedError,
} from "../../lib/push";
import { ApiError } from "../../lib/api";
import { ScopeUpgradeModal } from "../common/ScopeUpgradeModal";

interface CreateIssueModalProps {
  isOpen: boolean;
  onClose: () => void;
  repoId: number | string;
  repoIdentifier: string;
  userPreferredLanguage?: string;
  onSuccess?: (issueUrl: string, issueNumber: number) => void;
}

type Step = "compose" | "translate" | "result";

export function CreateIssueModal({
  isOpen,
  onClose,
  repoId,
  repoIdentifier,
  userPreferredLanguage = "en",
  onSuccess,
}: CreateIssueModalProps) {
  const [step, setStep] = useState<Step>("compose");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [writtenIn, setWrittenIn] = useState(userPreferredLanguage);

  const [preview, setPreview] = useState<IssuePreviewResponse | null>(null);
  const [editedTitle, setEditedTitle] = useState("");
  const [editedBody, setEditedBody] = useState("");

  const [isLoading, setIsLoading] = useState(false);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [showScopeUpgrade, setShowScopeUpgrade] = useState(false);

  const [resultUrl, setResultUrl] = useState<string>("");
  const [resultNumber, setResultNumber] = useState<number | null>(null);

  if (!isOpen) return null;

  const numericRepoId = typeof repoId === "string" ? parseInt(repoId, 10) : repoId;

  const handlePreview = async () => {
    if (!title.trim()) {
      setErrorBanner("Issue title is required.");
      return;
    }

    setIsLoading(true);
    setErrorBanner(null);

    try {
      const data = await createIssuePreview(numericRepoId, {
        title: title.trim(),
        body: body.trim(),
        written_in: writtenIn,
      });

      setPreview(data);
      setEditedTitle(data.texts.title.translated);
      setEditedBody(data.texts.body.translated);
      setStep("translate");
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 403 && err.detail.includes("scope_required")) {
          setShowScopeUpgrade(true);
          return;
        }
        const errBody = err.body as { detail?: SecretDetectedError } | undefined;
        if (errBody?.detail?.error === "secret_detected") {
          setErrorBanner("Blocked: Secrets detected in issue text. Please remove them.");
          return;
        }
        setErrorBanner(err.detail);
      } else {
        setErrorBanner(err instanceof Error ? err.message : "Failed to create preview");
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
      // If user modified the translated text, update before confirming
      if (
        editedTitle !== preview.texts.title.translated ||
        editedBody !== preview.texts.body.translated
      ) {
        await editIssuePreview(numericRepoId, preview.preview_id, {
          title: editedTitle,
          body: editedBody,
        });
      }

      const res = await confirmIssue(numericRepoId, preview.preview_id);
      setResultUrl(res.issue_url);
      setResultNumber(res.number);
      setStep("result");
      if (onSuccess) {
        onSuccess(res.issue_url, res.number);
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 403 && err.detail.includes("scope_required")) {
          setShowScopeUpgrade(true);
          return;
        }
        setErrorBanner(err.detail);
      } else {
        setErrorBanner(err instanceof Error ? err.message : "Failed to create issue");
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
        <div className="w-full max-w-xl rounded-2xl bg-neutral-900 border border-neutral-800 shadow-2xl flex flex-col max-h-[90vh] overflow-hidden text-neutral-100">
          {/* Modal Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-neutral-800 bg-neutral-950/50">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-orange-500/10 border border-orange-500/30 flex items-center justify-center text-orange-400 font-bold">
                📋
              </div>
              <div>
                <h2 className="text-base font-bold text-neutral-100">
                  New Issue on GitHub
                </h2>
                <p className="text-xs text-neutral-400 font-mono">{repoIdentifier}</p>
              </div>
            </div>

            {step !== "result" && (
              <button
                type="button"
                onClick={onClose}
                disabled={isLoading}
                className="p-1.5 rounded-lg text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800 cursor-pointer disabled:opacity-50"
              >
                ✕
              </button>
            )}
          </div>

          {/* Error Banner */}
          {errorBanner && (
            <div className="mx-6 mt-4 p-3 rounded-xl bg-rose-950/40 border border-rose-800/60 text-xs text-rose-300 flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                <span>⚠️</span>
                <span>{errorBanner}</span>
              </div>
              <button
                type="button"
                onClick={() => setErrorBanner(null)}
                className="text-rose-400 hover:text-rose-200 cursor-pointer text-xs"
              >
                ✕
              </button>
            </div>
          )}

          {/* Step 1: Compose */}
          {step === "compose" && (
            <div className="p-6 space-y-4 overflow-y-auto flex-1 text-xs">
              <div className="space-y-1.5">
                <label className="font-semibold text-neutral-300">
                  Issue Title <span className="text-orange-400">*</span>
                </label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g. Broken layout on mobile screens"
                  className="w-full px-3 py-2 rounded-xl bg-neutral-950 border border-neutral-800 text-xs text-neutral-100 focus:outline-none focus:border-orange-500"
                />
              </div>

              <div className="space-y-1.5">
                <label className="font-semibold text-neutral-300">Issue Description</label>
                <textarea
                  rows={6}
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                  placeholder="Describe the issue, steps to reproduce, and expected behavior in your language..."
                  className="w-full px-3 py-2 rounded-xl bg-neutral-950 border border-neutral-800 text-xs text-neutral-100 focus:outline-none focus:border-orange-500 resize-none font-mono"
                />
              </div>

              <div className="space-y-1.5">
                <label className="font-semibold text-neutral-300">I wrote this in</label>
                <select
                  value={writtenIn}
                  onChange={(e) => setWrittenIn(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-neutral-950 border border-neutral-800 text-xs text-neutral-200 focus:outline-none focus:border-orange-500"
                >
                  <option value="en">English (en)</option>
                  <option value="hi">Hindi (hi - हिन्दी)</option>
                  <option value="es">Spanish (es - Español)</option>
                  <option value="fr">French (fr - Français)</option>
                  <option value="de">German (de - Deutsch)</option>
                  <option value="ja">Japanese (ja - 日本語)</option>
                  <option value="zh">Chinese (zh - 中文)</option>
                  <option value="pt">Portuguese (pt - Português)</option>
                  <option value="ru">Russian (ru - Русский)</option>
                  <option value="ta">Tamil (ta - தமிழ்)</option>
                  <option value="te">Telugu (te - తెలుగు)</option>
                  <option value="bn">Bengali (bn - বাংলা)</option>
                </select>
              </div>
            </div>
          )}

          {/* Step 2: Translation Preview */}
          {step === "translate" && preview && (
            <div className="p-6 space-y-4 overflow-y-auto flex-1 text-xs">
              <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs flex items-center gap-2">
                <span>ℹ️</span>
                <span>
                  Machine translation into repository language (
                  <strong className="text-amber-200">{preview.repo_language}</strong>). Review and edit
                  before submitting.
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Original Column */}
                <div className="p-4 rounded-xl bg-neutral-950/60 border border-neutral-800 space-y-3">
                  <div className="font-bold text-neutral-400 uppercase tracking-wider text-[10px] pb-1 border-b border-neutral-800">
                    Your Text ({preview.written_in})
                  </div>
                  <div>
                    <span className="text-[10px] text-neutral-500 font-semibold block">Title</span>
                    <p className="text-neutral-200 mt-0.5">{preview.texts.title.original}</p>
                  </div>
                  <div>
                    <span className="text-[10px] text-neutral-500 font-semibold block">Body</span>
                    <p className="text-neutral-300 mt-0.5 whitespace-pre-wrap">
                      {preview.texts.body.original || "(No body)"}
                    </p>
                  </div>
                </div>

                {/* Translated Column (Editable) */}
                <div className="p-4 rounded-xl bg-orange-950/15 border border-orange-500/30 space-y-3">
                  <div className="font-bold text-orange-400 uppercase tracking-wider text-[10px] pb-1 border-b border-orange-500/20 flex items-center justify-between">
                    <span>Repository Text ({preview.repo_language})</span>
                    <span className="text-[9px] text-neutral-400 font-normal">Editable</span>
                  </div>
                  <div className="space-y-1">
                    <label className="text-[10px] text-neutral-400 font-semibold">Title</label>
                    <input
                      type="text"
                      value={editedTitle}
                      onChange={(e) => setEditedTitle(e.target.value)}
                      className="w-full px-2.5 py-1.5 rounded-lg bg-neutral-900 border border-neutral-700 text-xs text-neutral-100 focus:outline-none focus:border-orange-500"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-[10px] text-neutral-400 font-semibold">Body</label>
                    <textarea
                      rows={6}
                      value={editedBody}
                      onChange={(e) => setEditedBody(e.target.value)}
                      className="w-full px-2.5 py-1.5 rounded-lg bg-neutral-900 border border-neutral-700 text-xs text-neutral-100 focus:outline-none focus:border-orange-500 resize-none font-mono"
                    />
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Step 3: Result */}
          {step === "result" && (
            <div className="p-8 text-center space-y-5 flex-1 flex flex-col items-center justify-center">
              <div className="w-16 h-16 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 flex items-center justify-center text-3xl shadow-lg shadow-emerald-500/10">
                ✓
              </div>

              <div className="space-y-1">
                <h3 className="text-lg font-bold text-neutral-100">Issue Created!</h3>
                <p className="text-xs text-neutral-400">
                  Issue #{resultNumber} has been opened on GitHub.
                </p>
              </div>

              <div className="flex items-center gap-3 pt-2">
                <a
                  href={resultUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="px-5 py-2.5 rounded-xl text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-600/20 transition-all flex items-center gap-2 cursor-pointer"
                >
                  <span>View Issue on GitHub</span>
                  <span>&nearr;</span>
                </a>
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2.5 rounded-xl text-xs font-medium text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800 transition-colors cursor-pointer"
                >
                  Close
                </button>
              </div>
            </div>
          )}

          {/* Modal Footer */}
          {step !== "result" && (
            <div className="flex items-center justify-between px-6 py-4 border-t border-neutral-800 bg-neutral-950/50">
              <div>
                {step === "translate" && (
                  <button
                    type="button"
                    onClick={() => setStep("compose")}
                    disabled={isLoading}
                    className="px-3.5 py-1.5 rounded-lg text-xs font-medium text-neutral-400 hover:text-neutral-200 cursor-pointer disabled:opacity-50"
                  >
                    &larr; Back to edit
                  </button>
                )}
              </div>

              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={onClose}
                  disabled={isLoading}
                  className="px-4 py-2 rounded-xl text-xs font-medium text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800 transition-colors cursor-pointer disabled:opacity-50"
                >
                  Cancel
                </button>

                {step === "compose" && (
                  <button
                    type="button"
                    onClick={handlePreview}
                    disabled={isLoading || !title.trim()}
                    className="px-4 py-2 rounded-xl text-xs font-semibold bg-orange-500 hover:bg-orange-600 disabled:opacity-40 disabled:cursor-not-allowed text-white shadow-lg shadow-orange-500/20 transition-all cursor-pointer flex items-center gap-2"
                  >
                    {isLoading && (
                      <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    )}
                    <span>Preview & Translate &rarr;</span>
                  </button>
                )}

                {step === "translate" && (
                  <button
                    type="button"
                    onClick={handleConfirm}
                    disabled={isLoading}
                    className="px-5 py-2 rounded-xl text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed text-white shadow-lg shadow-emerald-600/20 transition-all cursor-pointer flex items-center gap-2"
                  >
                    {isLoading && (
                      <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    )}
                    <span>Confirm & Create Issue</span>
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      <ScopeUpgradeModal
        isOpen={showScopeUpgrade}
        onClose={() => setShowScopeUpgrade(false)}
        neededScope="public_repo"
      />
    </>
  );
}
