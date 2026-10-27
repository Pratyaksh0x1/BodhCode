import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { useRepoReadme } from "../../lib/repos";
import { useLanguages } from "../../lib/settings";

interface ReadmeTabProps {
  repoId: number | string;
  preferredLanguage?: string;
}

export function ReadmeTab({ repoId, preferredLanguage }: ReadmeTabProps) {
  const [showOriginal, setShowOriginal] = useState(false);
  const [refresh, setRefresh] = useState(false);

  const { data: readme, isLoading, isError, error, refetch } = useRepoReadme(
    repoId,
    preferredLanguage,
    refresh
  );
  const { data: languages } = useLanguages();

  const getLanguageName = (code: string | null | undefined): string => {
    if (!code) return "";
    const found = languages?.find((l) => l.code.toLowerCase() === code.toLowerCase());
    return found ? found.english_name : code.toUpperCase();
  };

  if (isLoading) {
    return (
      <div className="p-8 rounded-2xl border border-neutral-800 bg-neutral-900/40 space-y-4 animate-pulse">
        <div className="h-6 w-48 bg-neutral-800 rounded" />
        <div className="h-4 w-full bg-neutral-800/60 rounded" />
        <div className="h-4 w-5/6 bg-neutral-800/60 rounded" />
        <div className="h-4 w-4/6 bg-neutral-800/60 rounded" />
      </div>
    );
  }

  if (isError || !readme) {
    return (
      <div className="p-6 rounded-2xl border border-rose-900/40 bg-rose-950/20 text-rose-300 space-y-2">
        <h3 className="font-semibold text-rose-200">Failed to load README</h3>
        <p className="text-sm">{error?.message || "Could not retrieve repository README."}</p>
        <button
          onClick={() => refetch()}
          className="mt-2 px-3 py-1 text-xs rounded bg-rose-900/40 hover:bg-rose-800/40 border border-rose-700/50 text-rose-200 cursor-pointer"
        >
          Retry
        </button>
      </div>
    );
  }

  const isTranslated = Boolean(
    readme.translated &&
      readme.source_lang &&
      readme.target_lang &&
      readme.source_lang !== readme.target_lang
  );

  const sourceName = getLanguageName(readme.source_lang);
  const targetName = getLanguageName(readme.target_lang);

  const displayedContent =
    showOriginal || !readme.translated ? readme.original : readme.translated;

  const handleRetry = () => {
    setRefresh(true);
    refetch();
  };

  return (
    <div className="space-y-4">
      {/* Top Banner / Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-xl border border-neutral-800 bg-neutral-900/70 text-xs">
        <div className="flex items-center gap-2">
          <span className="font-mono font-medium text-neutral-300 px-2 py-0.5 rounded bg-neutral-800">
            {readme.file_name}
          </span>

          {isTranslated && (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-orange-500/10 text-orange-400 border border-orange-500/20 font-medium">
              <span>Translated from {sourceName} → {targetName}</span>
            </span>
          )}
        </div>

        {isTranslated && (
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setShowOriginal(!showOriginal)}
              className="px-3 py-1 rounded-lg border border-neutral-700 bg-neutral-800 hover:bg-neutral-700 text-neutral-200 font-medium transition-colors cursor-pointer flex items-center gap-1.5"
            >
              <span>{showOriginal ? "Show translation" : "Show original"}</span>
            </button>
          </div>
        )}
      </div>

      {/* Busy fallback warning */}
      {readme.reason === "busy" && (
        <div className="p-3.5 rounded-xl border border-amber-900/50 bg-amber-950/20 text-amber-300 flex items-center justify-between text-xs">
          <span>Translation is busy — showing the original.</span>
          <button
            onClick={handleRetry}
            className="px-2.5 py-1 rounded bg-amber-900/40 hover:bg-amber-800/40 border border-amber-700/50 text-amber-200 font-medium cursor-pointer"
          >
            Retry
          </button>
        </div>
      )}

      {/* Markdown Content */}
      <div className="p-8 rounded-2xl border border-neutral-800 bg-neutral-900/30 prose prose-invert max-w-none text-neutral-300 text-sm leading-relaxed overflow-x-auto">
        <ReactMarkdown
          components={{
            a: ({ href, children }) => (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-orange-400 hover:text-orange-300 underline underline-offset-2"
              >
                {children}
              </a>
            ),
            img: ({ src, alt }) => (
              <img
                src={src}
                alt={alt}
                loading="lazy"
                className="max-w-full h-auto rounded my-3 border border-neutral-800"
              />
            ),
            code: ({ children, className }) => {
              const isInline = !className;
              if (isInline) {
                return (
                  <code className="px-1.5 py-0.5 rounded bg-neutral-800 font-mono text-xs text-orange-300">
                    {children}
                  </code>
                );
              }
              return (
                <code className="block p-4 rounded-xl bg-neutral-950 border border-neutral-800 font-mono text-xs overflow-x-auto text-neutral-200 my-3">
                  {children}
                </code>
              );
            },
          }}
        >
          {displayedContent}
        </ReactMarkdown>
      </div>
    </div>
  );
}
