interface StatusBarProps {
  language: string | null;
  cursorPos: { line: number; col: number };
  changesCount: number;
  repoIdentifier: string;
}

export function StatusBar({
  language,
  cursorPos,
  changesCount,
  repoIdentifier,
}: StatusBarProps) {
  return (
    <div className="h-6 bg-neutral-900 border-t border-neutral-800 text-neutral-400 text-[11px] px-3 flex items-center justify-between shrink-0 select-none">
      {/* Left items */}
      <div className="flex items-center gap-4">
        {language && (
          <span className="font-medium text-neutral-300">
            {language.charAt(0).toUpperCase() + language.slice(1)}
          </span>
        )}

        <span>
          Ln {cursorPos.line}, Col {cursorPos.col}
        </span>
      </div>

      {/* Right items */}
      <div className="flex items-center gap-4">
        {changesCount > 0 && (
          <span className="text-amber-400 font-medium flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
            <span>Graph reflects original commit ({changesCount} {changesCount === 1 ? "change" : "changes"})</span>
          </span>
        )}

        <span className="font-mono text-[10px] text-neutral-500">{repoIdentifier}</span>
      </div>
    </div>
  );
}
