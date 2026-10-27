interface AiAssistantPlaceholderProps {
  onClose?: () => void;
}

export function AiAssistantPlaceholder({ onClose }: AiAssistantPlaceholderProps) {
  return (
    <div className="h-full flex flex-col bg-neutral-950 border-l border-neutral-800 text-neutral-400 select-none overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 bg-neutral-900 border-b border-neutral-800 text-xs font-semibold shrink-0">
        <div className="flex items-center gap-1.5 text-neutral-300">
          <span className="text-orange-400">✨</span>
          <span>AI Assistant</span>
          <span className="text-[10px] px-1.5 py-0.2 rounded bg-neutral-800 text-neutral-400 font-normal">
            Phase 12
          </span>
        </div>

        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800 cursor-pointer"
          >
            ✕
          </button>
        )}
      </div>

      {/* Placeholder Content */}
      <div className="flex-1 flex flex-col items-center justify-center p-6 text-center gap-3">
        <div className="w-12 h-12 rounded-2xl bg-orange-500/10 border border-orange-500/20 flex items-center justify-center text-xl text-orange-400">
          ✨
        </div>
        <div className="space-y-1 max-w-xs">
          <h4 className="text-sm font-semibold text-neutral-200">AI Coding Assistant</h4>
          <p className="text-xs text-neutral-500">
            Automated code generation, test proposal, and refactoring will be active in Phase 12.
          </p>
        </div>

        <button
          type="button"
          disabled
          className="mt-2 px-4 py-1.5 rounded-lg text-xs font-medium bg-neutral-800 text-neutral-500 cursor-not-allowed border border-neutral-700"
        >
          Assistant Inactive
        </button>
      </div>
    </div>
  );
}
