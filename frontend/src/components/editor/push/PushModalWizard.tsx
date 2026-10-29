import { useState, useMemo } from "react";
import type { ChangedFileItem } from "../../../lib/files";
import {
  createPushPreview,
  editPushPreview,
  confirmPush,
  type PushPreviewResponse,
  type SecretFinding,
  type SecretDetectedError,
} from "../../../lib/push";
import { ApiError } from "../../../lib/api";
import { ScopeUpgradeModal } from "../../common/ScopeUpgradeModal";

interface PushModalWizardProps {
  isOpen: boolean;
  onClose: () => void;
  repoId: number;
  upstreamRepo: string; // e.g. "facebook/react"
  changes: ChangedFileItem[];
  userPreferredLanguage?: string;
  onSuccess?: () => void;
}

type WizardStep = "review" | "compose" | "translate" | "confirm" | "result";

// Client-side quick check for prohibited filenames
const BLOCKED_FILENAME_PATTERNS = [
  /^\.env/i,
  /\.pem$/i,
  /^id_rsa/i,
  /\.key$/i,
  /^credentials/i,
  /^\.github\/workflows\//i,
];

function sanitizeBranchName(input: string): string {
  return input
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9/_-]/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

export function PushModalWizard({
  isOpen,
  onClose,
  repoId,
  upstreamRepo,
  changes,
  userPreferredLanguage = "en",
  onSuccess,
}: PushModalWizardProps) {
  const [step, setStep] = useState<WizardStep>("review");

  // Step 2 Compose state
  const [branchName, setBranchName] = useState("feat/bodhcode-update");
  const [commitMessage, setCommitMessage] = useState("");
  const [prTitle, setPrTitle] = useState("");
  const [prBody, setPrBody] = useState("");
  const [writtenIn, setWrittenIn] = useState(userPreferredLanguage);

  // Step 3 Translation state
  const [preview, setPreview] = useState<PushPreviewResponse | null>(null);
  const [editedCommitMessage, setEditedCommitMessage] = useState("");
  const [editedPrTitle, setEditedPrTitle] = useState("");
  const [editedPrBody, setEditedPrBody] = useState("");
  const [isTranslating, setIsTranslating] = useState(false);
  const [isSavingEdit, setIsSavingEdit] = useState(false);

  // Step 4 Confirm state
  const [hasConfirmedCheckbox, setHasConfirmedCheckbox] = useState(false);
  const [isPushing, setIsPushing] = useState(false);
  const [pushStatusMessage, setPushStatusMessage] = useState<string>("");

  // Step 5 Result state
  const [resultPrUrl, setResultPrUrl] = useState<string>("");
  const [resultBranchName, setResultBranchName] = useState<string>("");
  const [resultCommitSha, setResultCommitSha] = useState<string>("");

  // Scope escalation modal
  const [showScopeUpgrade, setShowScopeUpgrade] = useState(false);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [secretFindings, setSecretFindings] = useState<SecretFinding[]>([]);

  // Check if any change violates prohibited files
  const clientBlockedFiles = useMemo(() => {
    return changes.filter((c) =>
      BLOCKED_FILENAME_PATTERNS.some((pat) => pat.test(c.path))
    );
  }, [changes]);

  if (!isOpen) return null;

  // Step 1 -> Step 2
  const handleProceedToCompose = () => {
    if (clientBlockedFiles.length > 0) return;
    setErrorBanner(null);
    setSecretFindings([]);
    setStep("compose");
  };

  // Step 2 -> Step 3: Create Preview
  const handleCreatePreview = async () => {
    if (!commitMessage.trim()) {
      setErrorBanner("Commit message is required.");
      return;
    }
    const finalPrTitle = prTitle.trim() || commitMessage.trim();
    const finalBranch = sanitizeBranchName(branchName) || "feat/bodhcode-update";

    setIsTranslating(true);
    setErrorBanner(null);
    setSecretFindings([]);

    try {
      const data = await createPushPreview(repoId, {
        branch_name: finalBranch,
        commit_message: commitMessage.trim(),
        pr_title: finalPrTitle,
        pr_body: prBody.trim(),
        language_override: writtenIn,
      });

      setPreview(data);
      setEditedCommitMessage(data.texts.commit_message.translated);
      setEditedPrTitle(data.texts.pr_title.translated);
      setEditedPrBody(data.texts.pr_body.translated);
      setStep("translate");
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 403 && err.detail.includes("scope_required")) {
          setShowScopeUpgrade(true);
          return;
        }
        // Check for secret detection error
        const body = err.body as { detail?: SecretDetectedError } | undefined;
        if (body?.detail?.error === "secret_detected" && Array.isArray(body.detail.findings)) {
          setSecretFindings(body.detail.findings);
          setErrorBanner("Blocked: Secrets detected in changes. Please revert them before pushing.");
          setStep("review");
          return;
        }
        setErrorBanner(err.detail);
      } else {
        setErrorBanner(err instanceof Error ? err.message : "Failed to generate preview");
      }
    } finally {
      setIsTranslating(false);
    }
  };

  // Step 3: Save edits to translation preview
  const handleSaveTranslationEdits = async () => {
    if (!preview) return;
    setIsSavingEdit(true);
    setErrorBanner(null);

    try {
      const updated = await editPushPreview(repoId, preview.preview_id, {
        commit_message: editedCommitMessage,
        pr_title: editedPrTitle,
        pr_body: editedPrBody,
      });
      setPreview(updated);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setErrorBanner(err.detail);
      } else {
        setErrorBanner(err instanceof Error ? err.message : "Failed to save edits");
      }
    } finally {
      setIsSavingEdit(false);
    }
  };

  // Step 3 -> Step 4
  const handleProceedToConfirm = async () => {
    // If user edited any translation text, save before proceeding
    if (
      preview &&
      (editedCommitMessage !== preview.texts.commit_message.translated ||
        editedPrTitle !== preview.texts.pr_title.translated ||
        editedPrBody !== preview.texts.pr_body.translated)
    ) {
      await handleSaveTranslationEdits();
    }
    setStep("confirm");
  };

  // Step 4: Confirm push
  const handleConfirmPush = async () => {
    if (!preview || !hasConfirmedCheckbox) return;

    setIsPushing(true);
    setErrorBanner(null);
    setPushStatusMessage("Checking live permissions and preparing fork...");

    try {
      const result = await confirmPush(repoId, preview.preview_id);
      setResultPrUrl(result.pr_url);
      setResultBranchName(result.branch_name);
      setResultCommitSha(result.commit_sha);
      setStep("result");
      if (onSuccess) {
        onSuccess();
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 403 && err.detail.includes("scope_required")) {
          setShowScopeUpgrade(true);
          return;
        }
        if (err.status === 409 && err.detail.includes("modified")) {
          setErrorBanner("Working copy files were modified after preview. Please review and preview again.");
          setStep("review");
          return;
        }
        setErrorBanner(err.detail);
      } else {
        setErrorBanner(err instanceof Error ? err.message : "Push failed");
      }
    } finally {
      setIsPushing(false);
      setPushStatusMessage("");
    }
  };

  return (
    <>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
        <div className="w-full max-w-2xl rounded-2xl bg-neutral-900 border border-neutral-800 shadow-2xl flex flex-col max-h-[90vh] overflow-hidden text-neutral-100">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-neutral-800 bg-neutral-950/50">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-orange-500/10 border border-orange-500/30 flex items-center justify-center text-orange-400 font-bold">
                🚀
              </div>
              <div>
                <h2 className="text-base font-bold text-neutral-100">
                  Push Changes to GitHub
                </h2>
                <p className="text-xs text-neutral-400 font-mono">
                  {upstreamRepo} &bull; {changes.length} {changes.length === 1 ? "file" : "files"} changed
                </p>
              </div>
            </div>

            {step !== "result" && (
              <button
                type="button"
                onClick={onClose}
                disabled={isPushing}
                className="p-1.5 rounded-lg text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800 cursor-pointer disabled:opacity-50"
              >
                ✕
              </button>
            )}
          </div>

          {/* Stepper Progress Bar */}
          <div className="px-6 py-3 border-b border-neutral-800/80 bg-neutral-950/30 flex items-center justify-between text-xs font-medium">
            <span
              className={`flex items-center gap-1.5 ${
                step === "review" ? "text-orange-400 font-bold" : "text-neutral-400"
              }`}
            >
              <span className="w-5 h-5 rounded-full border flex items-center justify-center text-[10px] border-current">
                1
              </span>
              <span>Files</span>
            </span>
            <span className="text-neutral-600">&rarr;</span>
            <span
              className={`flex items-center gap-1.5 ${
                step === "compose" ? "text-orange-400 font-bold" : "text-neutral-400"
              }`}
            >
              <span className="w-5 h-5 rounded-full border flex items-center justify-center text-[10px] border-current">
                2
              </span>
              <span>Compose</span>
            </span>
            <span className="text-neutral-600">&rarr;</span>
            <span
              className={`flex items-center gap-1.5 ${
                step === "translate" ? "text-orange-400 font-bold" : "text-neutral-400"
              }`}
            >
              <span className="w-5 h-5 rounded-full border flex items-center justify-center text-[10px] border-current">
                3
              </span>
              <span>Translate</span>
            </span>
            <span className="text-neutral-600">&rarr;</span>
            <span
              className={`flex items-center gap-1.5 ${
                step === "confirm" ? "text-orange-400 font-bold" : "text-neutral-400"
              }`}
            >
              <span className="w-5 h-5 rounded-full border flex items-center justify-center text-[10px] border-current">
                4
              </span>
              <span>Confirm</span>
            </span>
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

          {/* Step 1: Review Files & Secret Scanner Check */}
          {step === "review" && (
            <div className="p-6 space-y-4 overflow-y-auto flex-1 text-xs">
              {(clientBlockedFiles.length > 0 || secretFindings.length > 0) && (
                <div className="p-4 rounded-xl bg-rose-950/50 border border-rose-800 text-rose-200 space-y-2">
                  <div className="font-bold flex items-center gap-2 text-sm text-rose-100">
                    <span>🛑</span>
                    <span>Push Blocked: Secrets or Restricted Files Detected</span>
                  </div>
                  <p>
                    BodhCode zero-trust security prohibits committing sensitive files (.env, keys, credentials)
                    or GitHub Actions workflow files directly from the browser.
                  </p>
                  <ul className="list-disc list-inside space-y-1 font-mono text-[11px] text-rose-300">
                    {clientBlockedFiles.map((f) => (
                      <li key={f.path}>
                        {f.path} (Restricted file type)
                      </li>
                    ))}
                    {secretFindings.map((f, i) => (
                      <li key={i}>
                        {f.path} ({f.rule_name})
                      </li>
                    ))}
                  </ul>
                  <p className="text-[11px] text-rose-300/80">
                    Please revert or remove these files in the Changes panel before pushing.
                  </p>
                </div>
              )}

              <div className="rounded-xl border border-neutral-800 bg-neutral-950/50 divide-y divide-neutral-800/60 overflow-hidden">
                <div className="px-4 py-2 bg-neutral-900/50 font-semibold text-neutral-300 flex items-center justify-between">
                  <span>Changed Files ({changes.length})</span>
                  <span className="text-[11px] text-neutral-500 font-normal">Status</span>
                </div>
                {changes.length === 0 ? (
                  <div className="p-6 text-center text-neutral-500">
                    No files changed in working copy.
                  </div>
                ) : (
                  changes.map((c) => (
                    <div key={c.path} className="px-4 py-2.5 flex items-center justify-between">
                      <span className="font-mono text-neutral-200 truncate">{c.path}</span>
                      <span
                        className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                          c.status === "modified"
                            ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                            : c.status === "added"
                            ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                            : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                        }`}
                      >
                        {c.status.toUpperCase()}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {/* Step 2: Compose in Your Language */}
          {step === "compose" && (
            <div className="p-6 space-y-4 overflow-y-auto flex-1 text-xs">
              <div className="space-y-1.5">
                <label className="font-semibold text-neutral-300 flex items-center justify-between">
                  <span>Feature Branch Name</span>
                  <span className="text-[11px] text-neutral-500 font-normal">
                    lowercase, alphanumeric, hyphens
                  </span>
                </label>
                <input
                  type="text"
                  value={branchName}
                  onChange={(e) => setBranchName(sanitizeBranchName(e.target.value))}
                  placeholder="feat/my-change"
                  className="w-full px-3 py-2 rounded-xl bg-neutral-950 border border-neutral-800 font-mono text-xs text-neutral-100 focus:outline-none focus:border-orange-500"
                />
              </div>

              <div className="space-y-1.5">
                <label className="font-semibold text-neutral-300">
                  Commit Message <span className="text-orange-400">*</span>
                </label>
                <input
                  type="text"
                  value={commitMessage}
                  onChange={(e) => {
                    setCommitMessage(e.target.value);
                    if (!prTitle) {
                      setPrTitle(e.target.value);
                    }
                  }}
                  placeholder="e.g. Add validation for search query input"
                  className="w-full px-3 py-2 rounded-xl bg-neutral-950 border border-neutral-800 text-xs text-neutral-100 focus:outline-none focus:border-orange-500"
                />
              </div>

              <div className="space-y-1.5">
                <label className="font-semibold text-neutral-300">Pull Request Title</label>
                <input
                  type="text"
                  value={prTitle}
                  onChange={(e) => setPrTitle(e.target.value)}
                  placeholder="e.g. Add validation for search query input"
                  className="w-full px-3 py-2 rounded-xl bg-neutral-950 border border-neutral-800 text-xs text-neutral-100 focus:outline-none focus:border-orange-500"
                />
              </div>

              <div className="space-y-1.5">
                <label className="font-semibold text-neutral-300">
                  Pull Request Body (Description)
                </label>
                <textarea
                  rows={4}
                  value={prBody}
                  onChange={(e) => setPrBody(e.target.value)}
                  placeholder="Describe your changes, why they are needed, and how they were tested..."
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

          {/* Step 3: Translation Preview (Editable Side-by-Side) */}
          {step === "translate" && preview && (
            <div className="p-6 space-y-4 overflow-y-auto flex-1 text-xs">
              <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span>ℹ️</span>
                  <span>
                    This is a machine translation into repository language (
                    <strong className="text-amber-200">{preview.repo_language}</strong>). Review and
                    edit before sending.
                  </span>
                </div>
              </div>

              {/* Side-by-Side Columns */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Left Column: Original */}
                <div className="p-4 rounded-xl bg-neutral-950/60 border border-neutral-800 space-y-3">
                  <div className="font-bold text-neutral-400 uppercase tracking-wider text-[10px] pb-1 border-b border-neutral-800">
                    Your Text ({preview.written_in})
                  </div>
                  <div>
                    <span className="text-[10px] text-neutral-500 block font-semibold">Commit Message</span>
                    <p className="text-neutral-200 mt-0.5">{preview.texts.commit_message.original}</p>
                  </div>
                  <div>
                    <span className="text-[10px] text-neutral-500 block font-semibold">PR Title</span>
                    <p className="text-neutral-200 mt-0.5">{preview.texts.pr_title.original}</p>
                  </div>
                  <div>
                    <span className="text-[10px] text-neutral-500 block font-semibold">PR Body</span>
                    <p className="text-neutral-300 mt-0.5 whitespace-pre-wrap">
                      {preview.texts.pr_body.original || "(No body provided)"}
                    </p>
                  </div>
                </div>

                {/* Right Column: Translated (Editable) */}
                <div className="p-4 rounded-xl bg-orange-950/15 border border-orange-500/30 space-y-3">
                  <div className="font-bold text-orange-400 uppercase tracking-wider text-[10px] pb-1 border-b border-orange-500/20 flex items-center justify-between">
                    <span>Repository Text ({preview.repo_language})</span>
                    <span className="text-[9px] text-neutral-400 font-normal">Editable</span>
                  </div>

                  <div className="space-y-1">
                    <label className="text-[10px] text-neutral-400 font-semibold">Commit Message</label>
                    <input
                      type="text"
                      value={editedCommitMessage}
                      onChange={(e) => setEditedCommitMessage(e.target.value)}
                      className="w-full px-2.5 py-1.5 rounded-lg bg-neutral-900 border border-neutral-700 text-xs text-neutral-100 focus:outline-none focus:border-orange-500"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-[10px] text-neutral-400 font-semibold">PR Title</label>
                    <input
                      type="text"
                      value={editedPrTitle}
                      onChange={(e) => setEditedPrTitle(e.target.value)}
                      className="w-full px-2.5 py-1.5 rounded-lg bg-neutral-900 border border-neutral-700 text-xs text-neutral-100 focus:outline-none focus:border-orange-500"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-[10px] text-neutral-400 font-semibold">PR Body</label>
                    <textarea
                      rows={4}
                      value={editedPrBody}
                      onChange={(e) => setEditedPrBody(e.target.value)}
                      className="w-full px-2.5 py-1.5 rounded-lg bg-neutral-900 border border-neutral-700 text-xs text-neutral-100 focus:outline-none focus:border-orange-500 resize-none font-mono"
                    />
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Step 4: Final Confirmation */}
          {step === "confirm" && preview && (
            <div className="p-6 space-y-4 overflow-y-auto flex-1 text-xs">
              <div className="p-4 rounded-xl bg-neutral-950/70 border border-neutral-800 space-y-3">
                <div className="font-bold text-neutral-200 text-sm">Push Summary</div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <span className="text-neutral-500 text-[11px] block">Target Repository</span>
                    <span className="font-mono text-neutral-200 font-semibold">
                      {preview.target_repo}
                    </span>
                    {preview.will_fork && (
                      <span className="ml-2 text-[10px] px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">
                        Fork
                      </span>
                    )}
                  </div>

                  <div>
                    <span className="text-neutral-500 text-[11px] block">Branch</span>
                    <span className="font-mono text-neutral-200">
                      {preview.head_branch} &rarr; {preview.base_branch}
                    </span>
                  </div>

                  <div>
                    <span className="text-neutral-500 text-[11px] block">Changed Files</span>
                    <span className="font-semibold text-neutral-200">
                      {preview.changes.length} {preview.changes.length === 1 ? "file" : "files"}
                    </span>
                  </div>

                  <div>
                    <span className="text-neutral-500 text-[11px] block">Repository Language</span>
                    <span className="font-semibold text-neutral-200 font-mono">
                      {preview.repo_language}
                    </span>
                  </div>
                </div>

                <div className="pt-2 border-t border-neutral-800 space-y-1">
                  <span className="text-neutral-500 text-[11px] block">Final PR Title:</span>
                  <p className="font-medium text-neutral-200">{editedPrTitle}</p>
                </div>
              </div>

              {/* Confirmation Checkbox */}
              <label className="flex items-start gap-3 p-3 rounded-xl border border-neutral-800 bg-neutral-950/40 hover:bg-neutral-950/60 cursor-pointer transition-colors">
                <input
                  type="checkbox"
                  checked={hasConfirmedCheckbox}
                  onChange={(e) => setHasConfirmedCheckbox(e.target.checked)}
                  className="mt-0.5 rounded text-orange-500 focus:ring-orange-500 border-neutral-700 bg-neutral-900 cursor-pointer"
                />
                <span className="text-xs text-neutral-300 select-none">
                  I reviewed the text and files and agree to push these changes to GitHub.
                </span>
              </label>

              {/* Live progress indicator */}
              {isPushing && (
                <div className="p-3 rounded-xl bg-orange-950/30 border border-orange-500/30 text-orange-300 flex items-center gap-3">
                  <div className="w-4 h-4 border-2 border-orange-400 border-t-transparent rounded-full animate-spin shrink-0" />
                  <span>{pushStatusMessage || "Pushing to GitHub..."}</span>
                </div>
              )}
            </div>
          )}

          {/* Step 5: Success Result */}
          {step === "result" && (
            <div className="p-8 text-center space-y-5 flex-1 flex flex-col items-center justify-center">
              <div className="w-16 h-16 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 flex items-center justify-center text-3xl shadow-lg shadow-emerald-500/10">
                ✓
              </div>

              <div className="space-y-1">
                <h3 className="text-lg font-bold text-neutral-100">
                  Pull Request Created Successfully!
                </h3>
                <p className="text-xs text-neutral-400">
                  Your changes have been committed and submitted as a pull request.
                </p>
              </div>

              <div className="p-4 rounded-xl bg-neutral-950 border border-neutral-800 font-mono text-xs text-neutral-300 space-y-1 text-left w-full max-w-md">
                <div>
                  <span className="text-neutral-500">Branch: </span>
                  <span className="text-orange-400 font-semibold">{resultBranchName}</span>
                </div>
                {resultCommitSha && (
                  <div>
                    <span className="text-neutral-500">Commit: </span>
                    <span className="text-neutral-300">{resultCommitSha.slice(0, 7)}</span>
                  </div>
                )}
              </div>

              <div className="flex items-center gap-3 pt-2">
                <a
                  href={resultPrUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="px-5 py-2.5 rounded-xl text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-600/20 transition-all flex items-center gap-2 cursor-pointer"
                >
                  <span>View Pull Request on GitHub</span>
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

          {/* Footer Navigation Buttons */}
          {step !== "result" && (
            <div className="flex items-center justify-between px-6 py-4 border-t border-neutral-800 bg-neutral-950/50">
              <div>
                {step === "compose" && (
                  <button
                    type="button"
                    onClick={() => setStep("review")}
                    className="px-3.5 py-1.5 rounded-lg text-xs font-medium text-neutral-400 hover:text-neutral-200 cursor-pointer"
                  >
                    &larr; Back to files
                  </button>
                )}
                {step === "translate" && (
                  <button
                    type="button"
                    onClick={() => setStep("compose")}
                    className="px-3.5 py-1.5 rounded-lg text-xs font-medium text-neutral-400 hover:text-neutral-200 cursor-pointer"
                  >
                    &larr; Back to compose
                  </button>
                )}
                {step === "confirm" && (
                  <button
                    type="button"
                    onClick={() => setStep("translate")}
                    disabled={isPushing}
                    className="px-3.5 py-1.5 rounded-lg text-xs font-medium text-neutral-400 hover:text-neutral-200 cursor-pointer disabled:opacity-50"
                  >
                    &larr; Back to translation
                  </button>
                )}
              </div>

              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={onClose}
                  disabled={isPushing}
                  className="px-4 py-2 rounded-xl text-xs font-medium text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800 transition-colors cursor-pointer disabled:opacity-50"
                >
                  Cancel
                </button>

                {step === "review" && (
                  <button
                    type="button"
                    onClick={handleProceedToCompose}
                    disabled={changes.length === 0 || clientBlockedFiles.length > 0}
                    className="px-4 py-2 rounded-xl text-xs font-semibold bg-orange-500 hover:bg-orange-600 disabled:opacity-40 disabled:cursor-not-allowed text-white shadow-lg shadow-orange-500/20 transition-all cursor-pointer"
                  >
                    Next: Describe Changes &rarr;
                  </button>
                )}

                {step === "compose" && (
                  <button
                    type="button"
                    onClick={handleCreatePreview}
                    disabled={isTranslating || !commitMessage.trim()}
                    className="px-4 py-2 rounded-xl text-xs font-semibold bg-orange-500 hover:bg-orange-600 disabled:opacity-40 disabled:cursor-not-allowed text-white shadow-lg shadow-orange-500/20 transition-all cursor-pointer flex items-center gap-2"
                  >
                    {isTranslating && (
                      <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    )}
                    <span>Next: Review Translation &rarr;</span>
                  </button>
                )}

                {step === "translate" && (
                  <button
                    type="button"
                    onClick={handleProceedToConfirm}
                    disabled={isSavingEdit}
                    className="px-4 py-2 rounded-xl text-xs font-semibold bg-orange-500 hover:bg-orange-600 disabled:opacity-40 disabled:cursor-not-allowed text-white shadow-lg shadow-orange-500/20 transition-all cursor-pointer flex items-center gap-2"
                  >
                    {isSavingEdit && (
                      <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    )}
                    <span>Next: Confirm Push &rarr;</span>
                  </button>
                )}

                {step === "confirm" && (
                  <button
                    type="button"
                    onClick={handleConfirmPush}
                    disabled={!hasConfirmedCheckbox || isPushing}
                    className="px-5 py-2 rounded-xl text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed text-white shadow-lg shadow-emerald-600/20 transition-all cursor-pointer flex items-center gap-2"
                  >
                    {isPushing && (
                      <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    )}
                    <span>Push to GitHub</span>
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Scope Upgrade Escort */}
      <ScopeUpgradeModal
        isOpen={showScopeUpgrade}
        onClose={() => setShowScopeUpgrade(false)}
        neededScope="public_repo"
      />
    </>
  );
}
