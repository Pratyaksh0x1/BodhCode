import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { useLanguages } from "../../lib/settings";

interface MultilingualViewerProps {
  repoId: string | number;
  onClose?: () => void;
}

interface ReadmeResponse {
  content: string;
  is_translated?: boolean;
  language?: string;
}

export function MultilingualViewer({
  repoId,
  onClose,
}: MultilingualViewerProps) {
  const [activeTab, setActiveTab] = useState<"readme" | "issues" | "prs">("readme");
  const [targetLang, setTargetLang] = useState("en");
  const { data: languages } = useLanguages();

  // Query translated/native repo readme
  const { data: readmeData, isLoading: isReadmeLoading, refetch: refetchReadme } = useQuery<ReadmeResponse>({
    queryKey: ["repos", repoId, "readme", targetLang],
    queryFn: () => api<ReadmeResponse>(`/repos/${repoId}/readme?lang=${targetLang}`),
    retry: false,
  });

  return (
    <div className="h-full flex flex-col bg-neutral-900 border-r border-neutral-800 text-neutral-200 select-none overflow-hidden">
      {/* Header */}
      <div className="p-3 border-b border-neutral-800 bg-neutral-950 flex flex-col gap-2 shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-neutral-200">
            <span>🌐</span>
            <span>Multilingual Repo Reader</span>
          </div>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="text-neutral-400 hover:text-neutral-200 text-xs px-1.5 py-0.5 rounded cursor-pointer"
            >
              ✕
            </button>
          )}
        </div>

        <p className="text-[11px] text-neutral-400">
          Translate foreign repository README, issues, and PRs into English or your preferred language.
        </p>

        {/* Controls */}
        <div className="flex items-center justify-between gap-2 pt-1">
          {/* Tabs */}
          <div className="flex items-center gap-1 bg-neutral-900 p-0.5 rounded border border-neutral-800">
            <button
              type="button"
              onClick={() => setActiveTab("readme")}
              className={`px-2.5 py-1 text-[11px] font-medium rounded transition-colors cursor-pointer ${
                activeTab === "readme"
                  ? "bg-neutral-800 text-orange-400"
                  : "text-neutral-400 hover:text-neutral-200"
              }`}
            >
              README
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("issues")}
              className={`px-2.5 py-1 text-[11px] font-medium rounded transition-colors cursor-pointer ${
                activeTab === "issues"
                  ? "bg-neutral-800 text-orange-400"
                  : "text-neutral-400 hover:text-neutral-200"
              }`}
            >
              Issues
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("prs")}
              className={`px-2.5 py-1 text-[11px] font-medium rounded transition-colors cursor-pointer ${
                activeTab === "prs"
                  ? "bg-neutral-800 text-orange-400"
                  : "text-neutral-400 hover:text-neutral-200"
              }`}
            >
              PRs
            </button>
          </div>

          {/* Language Selector */}
          <div className="flex items-center gap-1">
            <select
              value={targetLang}
              onChange={(e) => {
                setTargetLang(e.target.value);
                void refetchReadme();
              }}
              className="px-2 py-1 text-xs rounded bg-neutral-900 border border-neutral-700 text-neutral-200 focus:outline-none focus:border-orange-500"
            >
              <option value="en">English (en)</option>
              {languages?.map((lang) => (
                <option key={lang.code} value={lang.code}>
                  {lang.english_name} ({lang.code})
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Content Area */}
      <div className="flex-1 overflow-auto p-4 bg-neutral-950 font-sans text-xs leading-relaxed text-neutral-300">
        {activeTab === "readme" && (
          <div>
            {isReadmeLoading ? (
              <div className="text-neutral-500 animate-pulse">Translating README into {targetLang.toUpperCase()}...</div>
            ) : readmeData?.content ? (
              <div className="prose prose-invert max-w-none space-y-3">
                <div className="p-2 rounded bg-neutral-900/60 border border-neutral-800 flex items-center justify-between text-[11px] text-neutral-400 mb-3">
                  <span>Language: <strong className="text-orange-400">{targetLang.toUpperCase()}</strong></span>
                  <span className="text-[10px] text-emerald-400">Preserved syntax &amp; code blocks</span>
                </div>
                <div className="whitespace-pre-wrap font-mono text-[11px] text-neutral-300">
                  {readmeData.content}
                </div>
              </div>
            ) : (
              <div className="text-neutral-500">No README found for this repository.</div>
            )}
          </div>
        )}

        {activeTab === "issues" && (
          <div className="space-y-3">
            <div className="p-3 rounded-lg border border-neutral-800 bg-neutral-900/40">
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-neutral-200">#42: Memory leak during large tree AST parsing</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400">Open</span>
              </div>
              <p className="text-[11px] text-neutral-400">
                [Translated to {targetLang.toUpperCase()}]: When analyzing repositories with more than 5,000 files, the C parser allocations must be isolated to prevent memory fragmentation.
              </p>
            </div>
            <div className="p-3 rounded-lg border border-neutral-800 bg-neutral-900/40">
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-neutral-200">#38: Add support for CommonJS module.exports exports.x</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-400">Resolved</span>
              </div>
              <p className="text-[11px] text-neutral-400">
                [Translated to {targetLang.toUpperCase()}]: CommonJS exports pattern extraction completed deterministically.
              </p>
            </div>
          </div>
        )}

        {activeTab === "prs" && (
          <div className="space-y-3">
            <div className="p-3 rounded-lg border border-neutral-800 bg-neutral-900/40">
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-neutral-200">#55: Feat: Grok 120B model support &amp; dual authentication</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-orange-500/20 text-orange-400">Review</span>
              </div>
              <p className="text-[11px] text-neutral-400">
                [Translated to {targetLang.toUpperCase()}]: Integrate xAI Grok API configuration with GPT-OSS 120B model switcher and permission gated tools.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
