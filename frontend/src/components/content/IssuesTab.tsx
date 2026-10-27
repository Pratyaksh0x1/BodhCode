import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { useRepoIssueDetail, useRepoIssues } from "../../lib/repos";

interface IssuesTabProps {
  repoId: number | string;
  preferredLanguage?: string;
}

export function IssuesTab({ repoId, preferredLanguage }: IssuesTabProps) {
  const [filterState, setFilterState] = useState<"open" | "closed" | "all">("open");
  const [page, setPage] = useState(1);
  const [selectedIssueNumber, setSelectedIssueNumber] = useState<number | null>(null);

  const { data: issuesData, isLoading, isError, error } = useRepoIssues(
    repoId,
    filterState,
    page,
    preferredLanguage
  );

  return (
    <div className="space-y-4">
      {/* Filters & Actions Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-xl border border-neutral-800 bg-neutral-900/60 text-xs">
        <div className="flex items-center gap-1.5">
          {(["open", "closed", "all"] as const).map((st) => (
            <button
              key={st}
              type="button"
              onClick={() => {
                setFilterState(st);
                setPage(1);
                setSelectedIssueNumber(null);
              }}
              className={`px-3 py-1 rounded-lg font-medium transition-colors cursor-pointer capitalize ${
                filterState === st
                  ? "bg-neutral-800 text-orange-400 border border-neutral-700"
                  : "text-neutral-400 hover:text-neutral-200 border border-transparent"
              }`}
            >
              {st}
            </button>
          ))}
        </div>

        {/* Pagination buttons */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            className="px-2.5 py-1 rounded border border-neutral-800 bg-neutral-900 text-neutral-400 disabled:opacity-40 disabled:cursor-not-allowed hover:text-neutral-200 cursor-pointer"
          >
            &larr; Prev
          </button>
          <span className="font-mono text-neutral-400">Page {page}</span>
          <button
            type="button"
            disabled={!issuesData?.next_page}
            onClick={() => setPage((p) => p + 1)}
            className="px-2.5 py-1 rounded border border-neutral-800 bg-neutral-900 text-neutral-400 disabled:opacity-40 disabled:cursor-not-allowed hover:text-neutral-200 cursor-pointer"
          >
            Next &rarr;
          </button>
        </div>
      </div>

      {/* Main View: Split or List + Detail */}
      {isLoading ? (
        <div className="p-8 rounded-2xl border border-neutral-800 bg-neutral-900/30 space-y-3 animate-pulse">
          <div className="h-10 w-full bg-neutral-800/60 rounded-xl" />
          <div className="h-10 w-full bg-neutral-800/60 rounded-xl" />
          <div className="h-10 w-full bg-neutral-800/60 rounded-xl" />
        </div>
      ) : isError || !issuesData ? (
        <div className="p-6 rounded-2xl border border-rose-900/40 bg-rose-950/20 text-rose-300">
          <p className="text-sm">{error?.message || "Failed to load issues."}</p>
        </div>
      ) : !issuesData.items || issuesData.items.length === 0 ? (
        <div className="p-12 text-center rounded-2xl border border-neutral-800 bg-neutral-900/20 text-neutral-500 text-sm">
          No {filterState} issues found.
        </div>
      ) : (
        <div className="space-y-3">
          {issuesData.items.map((issue) => {
            const isExpanded = selectedIssueNumber === issue.number;
            return (
              <div
                key={issue.number}
                className={`rounded-xl border transition-all ${
                  isExpanded
                    ? "border-orange-500/40 bg-neutral-900/90 shadow-lg shadow-orange-950/20"
                    : "border-neutral-800 bg-neutral-900/40 hover:border-neutral-700 hover:bg-neutral-900/60"
                }`}
              >
                {/* Issue Header / Row */}
                <div
                  onClick={() =>
                    setSelectedIssueNumber(isExpanded ? null : issue.number)
                  }
                  className="p-4 flex items-start justify-between gap-4 cursor-pointer"
                >
                  <div className="space-y-1.5 flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-xs text-neutral-500">
                        #{issue.number}
                      </span>
                      <span
                        className={`px-2 py-0.5 rounded-full text-[10px] font-medium uppercase border ${
                          issue.state === "open"
                            ? "bg-emerald-950/60 text-emerald-300 border-emerald-800/60"
                            : "bg-purple-950/60 text-purple-300 border-purple-800/60"
                        }`}
                      >
                        {issue.state}
                      </span>

                      {/* Display translated title if present, original title on hover / subline */}
                      <h4
                        className="font-semibold text-neutral-200 text-sm hover:text-orange-400 transition-colors"
                        title={
                          issue.translated_title
                            ? `Original: ${issue.original_title}`
                            : undefined
                        }
                      >
                        {issue.translated_title || issue.title}
                      </h4>

                      {issue.translated_title && (
                        <span className="px-1.5 py-0.2 rounded text-[10px] bg-orange-500/10 text-orange-400 border border-orange-500/20 font-medium">
                          Translated
                        </span>
                      )}
                    </div>

                    {/* Original title helper subtitle if translated */}
                    {issue.translated_title && (
                      <p className="text-xs text-neutral-500 font-sans italic truncate">
                        Orig: {issue.original_title}
                      </p>
                    )}

                    {/* Meta info & Labels */}
                    <div className="flex flex-wrap items-center gap-2 pt-1 text-xs text-neutral-500">
                      <span>opened by {issue.author.login}</span>
                      {issue.labels.map((lbl) => (
                        <span
                          key={lbl.name}
                          className="px-2 py-0.5 rounded-full text-[10px] font-medium border border-neutral-700 bg-neutral-800/80 text-neutral-300"
                        >
                          {lbl.name}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div className="flex items-center gap-3 text-xs text-neutral-400 shrink-0">
                    {issue.comment_count > 0 && (
                      <span className="flex items-center gap-1 font-mono text-neutral-400">
                        <span>💬</span>
                        <span>{issue.comment_count}</span>
                      </span>
                    )}
                    <a
                      href={issue.html_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="text-neutral-500 hover:text-neutral-300 transition-colors"
                      title="Open in GitHub"
                    >
                      ↗
                    </a>
                  </div>
                </div>

                {/* Expanded Lazy Detail View */}
                {isExpanded && (
                  <IssueDetailSection
                    repoId={repoId}
                    issueNumber={issue.number}
                    preferredLanguage={preferredLanguage}
                  />
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function IssueDetailSection({
  repoId,
  issueNumber,
  preferredLanguage,
}: {
  repoId: number | string;
  issueNumber: number;
  preferredLanguage?: string;
}) {
  const [showOriginalBody, setShowOriginalBody] = useState(false);
  const [originalCommentsMap, setOriginalCommentsMap] = useState<Record<number, boolean>>({});

  const { data: detail, isLoading, isError, error } = useRepoIssueDetail(
    repoId,
    issueNumber,
    preferredLanguage
  );

  if (isLoading) {
    return (
      <div className="p-6 border-t border-neutral-800 bg-neutral-950/40 space-y-3 animate-pulse">
        <div className="h-4 w-3/4 bg-neutral-800 rounded" />
        <div className="h-4 w-1/2 bg-neutral-800 rounded" />
      </div>
    );
  }

  if (isError || !detail) {
    return (
      <div className="p-4 border-t border-neutral-800 text-xs text-rose-300">
        {error?.message || "Failed to load issue description and comments."}
      </div>
    );
  }

  const toggleCommentOriginal = (id: number | null) => {
    if (id === null) return;
    setOriginalCommentsMap((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const hasTranslatedBody = Boolean(detail.translated_body && detail.translated_ok);
  const displayedBody =
    showOriginalBody || !hasTranslatedBody ? detail.original_body : detail.translated_body;

  return (
    <div className="p-6 border-t border-neutral-800 bg-neutral-950/30 space-y-6">
      {/* Issue Body */}
      <div className="space-y-3">
        <div className="flex items-center justify-between text-xs pb-2 border-b border-neutral-850">
          <span className="font-semibold text-neutral-300">Description</span>
          {hasTranslatedBody && (
            <button
              type="button"
              onClick={() => setShowOriginalBody(!showOriginalBody)}
              className="text-orange-400 hover:text-orange-300 transition-colors cursor-pointer"
            >
              {showOriginalBody ? "Show translation" : "Show original"}
            </button>
          )}
        </div>

        <div className="text-xs text-neutral-300 leading-relaxed prose prose-invert max-w-none">
          <ReactMarkdown
            components={{
              a: ({ href, children }) => (
                <a
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-orange-400 hover:underline"
                >
                  {children}
                </a>
              ),
              img: ({ src, alt }) => (
                <img src={src} alt={alt} loading="lazy" className="max-w-full rounded my-2" />
              ),
            }}
          >
            {displayedBody || "*No description provided.*"}
          </ReactMarkdown>
        </div>
      </div>

      {/* Comments Timeline */}
      {detail.comments && detail.comments.length > 0 && (
        <div className="space-y-4 pt-4 border-t border-neutral-800">
          <h5 className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
            Comments ({detail.comments.length})
          </h5>

          <div className="space-y-3">
            {detail.comments.map((comment, idx) => {
              const commentId = comment.id ?? idx;
              const isOriginal = Boolean(originalCommentsMap[commentId]);
              const hasTrans = Boolean(comment.translated_body && comment.translated_ok);
              const textToShow =
                isOriginal || !hasTrans ? comment.original_body : comment.translated_body;

              return (
                <div
                  key={commentId}
                  className="p-4 rounded-xl border border-neutral-800/80 bg-neutral-900/30 space-y-2 text-xs"
                >
                  <div className="flex items-center justify-between text-neutral-400">
                    <div className="flex items-center gap-2">
                      {comment.author.avatar_url && (
                        <img
                          src={comment.author.avatar_url}
                          alt={comment.author.login}
                          className="w-4 h-4 rounded-full"
                          loading="lazy"
                        />
                      )}
                      <span className="font-semibold text-neutral-200">
                        {comment.author.login}
                      </span>
                    </div>

                    {hasTrans && (
                      <button
                        type="button"
                        onClick={() => toggleCommentOriginal(commentId)}
                        className="text-orange-400 hover:text-orange-300 transition-colors cursor-pointer"
                      >
                        {isOriginal ? "Show translation" : "Show original"}
                      </button>
                    )}
                  </div>

                  <div className="text-neutral-300 leading-relaxed prose prose-invert max-w-none">
                    <ReactMarkdown
                      components={{
                        a: ({ href, children }) => (
                          <a
                            href={href}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-orange-400 hover:underline"
                          >
                            {children}
                          </a>
                        ),
                        img: ({ src, alt }) => (
                          <img
                            src={src}
                            alt={alt}
                            loading="lazy"
                            className="max-w-full rounded my-2"
                          />
                        ),
                      }}
                    >
                      {textToShow}
                    </ReactMarkdown>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
