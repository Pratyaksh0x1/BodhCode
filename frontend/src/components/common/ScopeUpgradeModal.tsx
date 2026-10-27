import { VITE_API_URL } from "../../lib/env";

interface ScopeUpgradeModalProps {
  isOpen: boolean;
  onClose: () => void;
  neededScope?: string;
  returnTo?: string;
}

export function ScopeUpgradeModal({
  isOpen,
  onClose,
  neededScope = "public_repo",
  returnTo,
}: ScopeUpgradeModalProps) {
  if (!isOpen) return null;

  const currentPath =
    returnTo || (typeof window !== "undefined" ? window.location.pathname + window.location.search : "/");
  const upgradeUrl = `${VITE_API_URL}/auth/github/upgrade?return_to=${encodeURIComponent(currentPath)}`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-md rounded-2xl bg-neutral-900 border border-neutral-800 p-6 shadow-2xl space-y-5 text-neutral-100">
        {/* Header */}
        <div className="flex items-start gap-4">
          <div className="w-10 h-10 rounded-xl bg-orange-500/10 border border-orange-500/30 flex items-center justify-center text-orange-400 shrink-0 text-lg">
            🔑
          </div>
          <div className="space-y-1">
            <h2 className="text-lg font-bold tracking-tight text-neutral-100">
              GitHub Permission Required
            </h2>
            <p className="text-xs text-neutral-400">
              Scope needed: <span className="font-mono text-orange-400">{neededScope}</span>
            </p>
          </div>
        </div>

        {/* Why BodhCode asks for public_repo */}
        <div className="space-y-3 rounded-xl bg-neutral-950/70 border border-neutral-800/80 p-4 text-xs text-neutral-300 leading-relaxed">
          <div className="font-semibold text-neutral-200 flex items-center gap-1.5">
            <span>🛡️</span>
            <span>Why BodhCode requests this permission</span>
          </div>
          <p>
            To push commits, create branches, or open Pull Requests and Issues on your behalf, GitHub
            requires the <code className="px-1 py-0.5 rounded bg-neutral-800 font-mono text-[11px] text-orange-300">public_repo</code> scope.
          </p>
          <ul className="space-y-1.5 list-disc list-inside text-neutral-400">
            <li>
              <strong className="text-neutral-300">Minimum privilege:</strong> Requested only when you
              choose to push.
            </li>
            <li>
              <strong className="text-neutral-300">Strictly isolated:</strong> BodhCode only interacts
              with repositories you explicitly open in the editor.
            </li>
            <li>
              <strong className="text-neutral-300">No private repos:</strong> BodhCode NEVER reads or
              accesses private repositories or repos you haven&apos;t opened.
            </li>
          </ul>
        </div>

        {/* Actions */}
        <div className="flex items-center justify-end gap-3 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-xl text-xs font-medium text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800 transition-colors cursor-pointer"
          >
            Cancel
          </button>
          <a
            href={upgradeUrl}
            className="px-4 py-2 rounded-xl text-xs font-semibold bg-orange-500 hover:bg-orange-600 text-white shadow-lg shadow-orange-500/20 transition-all flex items-center gap-1.5 cursor-pointer"
          >
            <span>Upgrade GitHub Permissions</span>
            <span>&rarr;</span>
          </a>
        </div>
      </div>
    </div>
  );
}
