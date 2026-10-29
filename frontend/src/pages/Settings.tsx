import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useDisconnect, type ReviewMode } from "../lib/auth";
import { getUserActivity } from "../lib/push";
import { useLanguages, useSettings } from "../lib/settings";
import {
  resolveEditorTheme,
  useThemeStore,
  type EditorThemePref,
  type ResolvedEditorTheme,
  type ThemePref,
} from "../lib/theme";

const EDITOR_THEME_OPTIONS: Array<{ value: EditorThemePref; label: string }> = [
  { value: "auto", label: "Auto (follow app theme)" },
  { value: "vs-dark", label: "Dark (VS Dark)" },
  { value: "vs", label: "Light (VS Light)" },
  { value: "hc-black", label: "High contrast dark" },
  { value: "hc-light", label: "High contrast light" },
];

export function Settings() {
  const { user, isLoading, updateSettings, isUpdating, error } = useSettings();
  const { data: languages, isLoading: isLanguagesLoading } = useLanguages();
  const resolvedAppTheme = useThemeStore((s) => s.resolved);

  const { data: activityLogs, isLoading: isActivityLoading } = useQuery({
    queryKey: ["user", "activity"],
    queryFn: () => getUserActivity(50),
  });

  const disconnect = useDisconnect();
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [deleteConfirmationInput, setDeleteConfirmationInput] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const handleConfirmDelete = async () => {
    if (deleteConfirmationInput.trim() !== "DELETE") return;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await disconnect();
    } catch (err: unknown) {
      setDeleteError(err instanceof Error ? err.message : "Failed to delete data");
      setIsDeleting(false);
    }
  };

  // Searchable language combobox state
  const [langSearch, setLangSearch] = useState("");
  const [langDropdownOpen, setLangDropdownOpen] = useState(false);
  const langDropdownRef = useRef<HTMLDivElement>(null);

  // Grok API Key & Model Configuration
  const [grokApiKeyInput, setGrokApiKeyInput] = useState("");
  const [showGrokKey, setShowGrokKey] = useState(false);
  const [customGrokModel, setCustomGrokModel] = useState<string | null>(null);
  const selectedGrokModel = customGrokModel ?? user?.grok_model ?? "gpt-oss-120b";

  const handleSaveGrokConfig = async () => {
    const payload: { grok_model?: string; grok_api_key?: string } = {
      grok_model: selectedGrokModel,
    };
    if (grokApiKeyInput.trim()) {
      payload.grok_api_key = grokApiKeyInput.trim();
    }
    await updateSettings(payload);
    setGrokApiKeyInput("");
    setCustomGrokModel(null);
    triggerSaved();
  };

  // "Saved" feedback indicator state
  const [showSaved, setShowSaved] = useState(false);
  const savedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (savedTimerRef.current) clearTimeout(savedTimerRef.current);
    };
  }, []);

  const triggerSaved = () => {
    setShowSaved(true);
    if (savedTimerRef.current) clearTimeout(savedTimerRef.current);
    savedTimerRef.current = setTimeout(() => setShowSaved(false), 2500);
  };

  // Close combobox on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (
        langDropdownRef.current &&
        !langDropdownRef.current.contains(e.target as Node)
      ) {
        setLangDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const currentLangCode = user?.preferred_language || "en";
  const currentTheme = (user?.theme as ThemePref) || "dark";
  const currentEditorTheme = (user?.editor_theme as EditorThemePref) || "auto";

  // Active language object
  const selectedLangObj = useMemo(() => {
    return languages?.find((l) => l.code === currentLangCode) || null;
  }, [languages, currentLangCode]);

  // Filtered languages for combobox
  const filteredLanguages = useMemo(() => {
    if (!languages) return [];
    const q = langSearch.trim().toLowerCase();
    if (!q) return languages;
    return languages.filter(
      (l) =>
        l.english_name.toLowerCase().includes(q) ||
        l.native_name.toLowerCase().includes(q) ||
        l.code.toLowerCase().includes(q)
    );
  }, [languages, langSearch]);

  const handleSelectLanguage = (code: string) => {
    updateSettings({ preferred_language: code }, { onSuccess: triggerSaved });
    setLangDropdownOpen(false);
    setLangSearch("");
  };

  const handleThemeChange = (theme: ThemePref) => {
    updateSettings({ theme }, { onSuccess: triggerSaved });
  };

  const handleEditorThemeChange = (editor_theme: EditorThemePref) => {
    updateSettings({ editor_theme }, { onSuccess: triggerSaved });
  };

  const currentReviewMode: ReviewMode = (user?.review_mode as ReviewMode) || "review";

  const handleReviewModeChange = (review_mode: ReviewMode) => {
    updateSettings({ review_mode }, { onSuccess: triggerSaved });
  };

  // Resolved editor theme for static preview block
  const previewEditorTheme: ResolvedEditorTheme = resolveEditorTheme(
    currentEditorTheme,
    resolvedAppTheme
  );

  if (isLoading) {
    return (
      <div className="py-24 flex flex-col items-center justify-center gap-3 text-neutral-400">
        <div className="w-8 h-8 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-sm">Loading your settings...</p>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-8 select-none">
      {/* Page Header with Live Status Feedback */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-neutral-200 dark:border-neutral-800">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight text-neutral-900 dark:text-neutral-100">
            Settings
          </h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
            Customize language translation preferences, app appearance, and editor themes.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {isUpdating && (
            <div className="flex items-center gap-2 text-xs font-medium text-orange-500 dark:text-orange-400">
              <div className="w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin" />
              <span>Saving...</span>
            </div>
          )}

          {showSaved && !isUpdating && (
            <div
              id="settings-saved-badge"
              role="status"
              className="px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border border-emerald-500/30 flex items-center gap-1.5 transition-opacity duration-300"
            >
              <span>✓</span>
              <span>Saved</span>
            </div>
          )}
        </div>
      </div>

      {/* Error Alert */}
      {error && (
        <div
          role="alert"
          className="p-4 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-300 dark:border-rose-800/80 text-rose-800 dark:text-rose-200 text-sm flex items-start gap-3 shadow-sm"
        >
          <span className="text-base shrink-0">⚠️</span>
          <div>
            <strong className="font-semibold block">Failed to save settings</strong>
            <p className="text-xs mt-0.5 opacity-90">{error.message}</p>
          </div>
        </div>
      )}

      {/* SECTION 1: Language */}
      <section
        aria-labelledby="language-section-heading"
        className="p-6 rounded-2xl bg-white dark:bg-neutral-900/60 border border-neutral-200 dark:border-neutral-800 shadow-sm space-y-4"
      >
        <div className="space-y-1">
          <h2
            id="language-section-heading"
            className="text-base font-bold text-neutral-900 dark:text-neutral-100"
          >
            Language
          </h2>
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            Repos in other languages — README, issues, pull requests — will be shown in this language.
          </p>
        </div>

        <div className="max-w-md relative" ref={langDropdownRef}>
          <label htmlFor="language-combobox" className="sr-only">
            Preferred Language
          </label>

          {/* Combobox trigger input */}
          <div className="relative">
            <input
              id="language-combobox"
              type="text"
              role="combobox"
              aria-expanded={langDropdownOpen}
              aria-autocomplete="list"
              value={langDropdownOpen ? langSearch : selectedLangObj ? `${selectedLangObj.native_name} · ${selectedLangObj.english_name}` : currentLangCode}
              placeholder="Search language..."
              onFocus={() => {
                setLangDropdownOpen(true);
                setLangSearch("");
              }}
              onChange={(e) => {
                setLangSearch(e.target.value);
                setLangDropdownOpen(true);
              }}
              className="w-full px-3.5 py-2 rounded-xl bg-neutral-50 dark:bg-neutral-800/60 border border-neutral-300 dark:border-neutral-700 text-xs font-medium text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-orange-500/60 shadow-xs cursor-pointer"
            />

            <button
              type="button"
              tabIndex={-1}
              onClick={() => setLangDropdownOpen((prev) => !prev)}
              aria-label="Toggle language dropdown"
              className="absolute right-3 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-200"
            >
              <svg
                className={`w-4 h-4 transition-transform ${langDropdownOpen ? "rotate-180" : ""}`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>
          </div>

          {/* Dropdown Options */}
          {langDropdownOpen && (
            <ul
              role="listbox"
              className="absolute left-0 right-0 mt-1.5 max-h-60 overflow-y-auto rounded-xl bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 shadow-2xl py-1 z-50 text-xs divide-y divide-neutral-100 dark:divide-neutral-800/60"
            >
              {isLanguagesLoading ? (
                <li className="px-3 py-2 text-neutral-400 italic">Loading languages catalogue...</li>
              ) : filteredLanguages.length === 0 ? (
                <li className="px-3 py-2 text-neutral-400 italic">No matching language found</li>
              ) : (
                filteredLanguages.map((lang) => {
                  const isSelected = lang.code === currentLangCode;
                  return (
                    <li
                      key={lang.code}
                      role="option"
                      aria-selected={isSelected}
                      onClick={() => handleSelectLanguage(lang.code)}
                      className={`px-3 py-2 cursor-pointer flex items-center justify-between transition-colors ${
                        isSelected
                          ? "bg-orange-500/10 text-orange-600 dark:text-orange-400 font-semibold"
                          : "text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800"
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <span>{lang.native_name}</span>
                        <span className="text-neutral-400 dark:text-neutral-500">&middot;</span>
                        <span className="opacity-80">{lang.english_name}</span>
                        {lang.rtl && (
                          <span className="text-[10px] px-1 py-0.2 rounded bg-neutral-200 dark:bg-neutral-800 text-neutral-500 font-mono">
                            RTL
                          </span>
                        )}
                      </div>

                      {isSelected && <span className="text-orange-500">✓</span>}
                    </li>
                  );
                })
              )}
            </ul>
          )}

          {/* RTL Language Note */}
          {selectedLangObj?.rtl && (
            <p className="mt-2 text-[11px] text-amber-600 dark:text-amber-400 flex items-center gap-1.5 font-medium">
              <span>ℹ️</span>
              <span>Note: This is a right-to-left (RTL) language.</span>
            </p>
          )}
        </div>
      </section>

      {/* SECTION 2: Appearance */}
      <section
        aria-labelledby="appearance-section-heading"
        className="p-6 rounded-2xl bg-white dark:bg-neutral-900/60 border border-neutral-200 dark:border-neutral-800 shadow-sm space-y-4"
      >
        <div className="space-y-1">
          <h2
            id="appearance-section-heading"
            className="text-base font-bold text-neutral-900 dark:text-neutral-100"
          >
            Appearance
          </h2>
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            Choose whether BodhCode displays in light or dark mode, or automatically follows your operating system.
          </p>
        </div>

        {/* Segmented Control */}
        <div
          role="radiogroup"
          aria-label="Theme mode"
          className="inline-flex p-1 rounded-xl bg-neutral-100 dark:bg-neutral-800/80 border border-neutral-200 dark:border-neutral-700/60 text-xs"
        >
          {(
            [
              { value: "system", label: "System", icon: "💻" },
              { value: "light", label: "Light", icon: "☀️" },
              { value: "dark", label: "Dark", icon: "🌙" },
            ] as const
          ).map((item) => {
            const isSelected = currentTheme === item.value;
            return (
              <button
                key={item.value}
                type="button"
                role="radio"
                aria-checked={isSelected}
                onClick={() => handleThemeChange(item.value)}
                className={`px-4 py-2 rounded-lg font-medium flex items-center gap-2 transition-all cursor-pointer focus:outline-none focus:ring-2 focus:ring-orange-500/60 ${
                  isSelected
                    ? "bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 shadow-xs border border-neutral-200/80 dark:border-neutral-700"
                    : "text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200"
                }`}
              >
                <span>{item.icon}</span>
                <span>{item.label}</span>
              </button>
            );
          })}
        </div>
      </section>

      {/* SECTION 3: Editor Theme */}
      <section
        aria-labelledby="editor-theme-section-heading"
        className="p-6 rounded-2xl bg-white dark:bg-neutral-900/60 border border-neutral-200 dark:border-neutral-800 shadow-sm space-y-4"
      >
        <div className="space-y-1">
          <h2
            id="editor-theme-section-heading"
            className="text-base font-bold text-neutral-900 dark:text-neutral-100"
          >
            Editor theme
          </h2>
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            Select the syntax color theme for in-browser code previews and editing.
          </p>
        </div>

        {/* Dropdown Selector */}
        <div className="max-w-md">
          <label htmlFor="editor-theme-select" className="sr-only">
            Editor Theme
          </label>
          <select
            id="editor-theme-select"
            value={currentEditorTheme}
            onChange={(e) => handleEditorThemeChange(e.target.value as EditorThemePref)}
            className="w-full px-3.5 py-2 rounded-xl bg-neutral-50 dark:bg-neutral-800/60 border border-neutral-300 dark:border-neutral-700 text-xs font-medium text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-orange-500/60 shadow-xs cursor-pointer"
          >
            {EDITOR_THEME_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        {/* Static Styled Code Preview Block */}
        <div className="space-y-2 pt-2">
          <span className="text-[11px] font-mono text-neutral-400 uppercase tracking-wider block">
            Theme Preview ({previewEditorTheme})
          </span>

          <div
            className={`p-4 rounded-xl font-mono text-xs overflow-x-auto border transition-colors shadow-inner ${
              previewEditorTheme === "vs-dark"
                ? "bg-[#1e1e1e] border-[#333333] text-[#d4d4d4]"
                : previewEditorTheme === "vs"
                ? "bg-[#ffffff] border-[#e0e0e0] text-[#000000]"
                : previewEditorTheme === "hc-black"
                ? "bg-[#000000] border-[#6fc3df] text-[#ffffff]"
                : "bg-[#ffffff] border-[#000000] text-[#000000]"
            }`}
          >
            <pre className="leading-relaxed">
              <code>
                <span className="text-emerald-500 dark:text-emerald-400">
                  {"// BodhCode dependency analysis"}
                </span>
                {"\n"}
                <span className="text-sky-500 dark:text-sky-400 font-bold">import</span>
                {" { analyzeRepo } "}
                <span className="text-sky-500 dark:text-sky-400 font-bold">from</span>
                {" "}
                <span className="text-amber-500 dark:text-amber-400">"bodhcode"</span>
                {";\n\n"}
                <span className="text-sky-500 dark:text-sky-400 font-bold">export async function</span>
                {" "}
                <span className="text-yellow-600 dark:text-yellow-300 font-semibold">buildMap</span>
                {"(repoId: "}
                <span className="text-emerald-600 dark:text-emerald-300">string</span>
                {") {\n"}
                {"  "}
                <span className="text-sky-500 dark:text-sky-400 font-bold">const</span>
                {" graph = "}
                <span className="text-sky-500 dark:text-sky-400 font-bold">await</span>
                {" analyzeRepo(repoId);\n"}
                {"  "}
                <span className="text-violet-500 dark:text-violet-400 font-bold">return</span>
                {" graph.stats.files;\n"}
                {"}"}
              </code>
            </pre>
          </div>
        </div>
      </section>

      {/* SECTION 4: AI Coding Agent */}
      <section
        aria-labelledby="agent-section-heading"
        className="p-6 rounded-2xl bg-white dark:bg-neutral-900/60 border border-neutral-200 dark:border-neutral-800 shadow-sm space-y-4"
      >
        <div className="space-y-1">
          <h2
            id="agent-section-heading"
            className="text-base font-bold text-neutral-900 dark:text-neutral-100"
          >
            AI Coding Agent Review Policy
          </h2>
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            Control how proposed code changes are reviewed before they are written to your working copy.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {(
            [
              {
                value: "review" as const,
                title: "Review every change",
                badge: "Recommended",
                desc: "Every edit or file creation becomes a proposal card with a diff and blast radius. You inspect and accept before files change.",
              },
              {
                value: "auto" as const,
                title: "Auto-accept edits",
                badge: "Fast",
                desc: "Creates and edits apply immediately with one-click Undo available. Deletions still queue for confirmation.",
              },
              {
                value: "readonly" as const,
                title: "Read-only plan",
                badge: "Plan Only",
                desc: "Agent cannot write files. Proposes plans, explanations, and architectural roadmaps in text only.",
              },
            ] as const
          ).map((item) => {
            const isSelected = currentReviewMode === item.value;
            return (
              <button
                key={item.value}
                type="button"
                onClick={() => handleReviewModeChange(item.value)}
                className={`p-4 rounded-xl border text-left transition-all cursor-pointer flex flex-col justify-between gap-3 ${
                  isSelected
                    ? "bg-orange-500/10 border-orange-500/40 text-neutral-900 dark:text-neutral-100 ring-2 ring-orange-500/20"
                    : "bg-neutral-50 dark:bg-neutral-900/40 border-neutral-200 dark:border-neutral-800 hover:border-neutral-300 dark:hover:border-neutral-700 text-neutral-600 dark:text-neutral-400"
                }`}
              >
                <div className="space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-xs text-neutral-900 dark:text-neutral-100">
                      {item.title}
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-neutral-200 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-300 font-medium">
                      {item.badge}
                    </span>
                  </div>
                  <p className="text-[11px] leading-relaxed text-neutral-500 dark:text-neutral-400">
                    {item.desc}
                  </p>
                </div>

                <div className="flex items-center gap-1 text-[11px] font-medium">
                  {isSelected ? (
                    <span className="text-orange-500 flex items-center gap-1">
                      <span>✓</span> Active Policy
                    </span>
                  ) : (
                    <span className="text-neutral-400">Select</span>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      </section>

      {/* Grok / xAI Models & API Configuration */}
      <section className="space-y-4 pt-4 border-t border-neutral-200 dark:border-neutral-800">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
              <span>🤖</span>
              <span>AI Agent & Grok / xAI Models</span>
            </h2>
            <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
              Configure Grok API key and choose from GPT-OSS 120B, Grok 2, or customized endpoints.
            </p>
          </div>
          <span
            className={`text-xs px-2.5 py-1 rounded-full font-medium ${
              user?.grok_configured
                ? "bg-emerald-500/10 text-emerald-500 border border-emerald-500/20"
                : "bg-neutral-100 dark:bg-neutral-800 text-neutral-500"
            }`}
          >
            {user?.grok_configured ? "Grok API Configured" : "Default Provider Active"}
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Model Selection */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-neutral-700 dark:text-neutral-300">
              Selected Grok Model
            </label>
            <select
              value={selectedGrokModel}
              onChange={(e) => setCustomGrokModel(e.target.value)}
              className="w-full px-3 py-2 text-xs rounded-lg border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-orange-500"
            >
              <option value="gpt-oss-120b">GPT-OSS 120B (High-Performance Open Weights)</option>
              <option value="grok-2">Grok 2 (Advanced Reasoning & Coding)</option>
              <option value="grok-beta">Grok Beta</option>
              <option value="grok-vision-beta">Grok Vision Beta (Multimodal)</option>
            </select>
          </div>

          {/* Grok API Key Input */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-neutral-700 dark:text-neutral-300">
              xAI / Grok API Key
            </label>
            <div className="relative flex items-center">
              <input
                type={showGrokKey ? "text" : "password"}
                value={grokApiKeyInput}
                onChange={(e) => setGrokApiKeyInput(e.target.value)}
                placeholder={
                  user?.grok_configured
                    ? "•••••••••••••••• (Configured — enter new key to replace)"
                    : "Enter xAI Grok API key (xai-...)"
                }
                className="w-full px-3 py-2 pr-16 text-xs rounded-lg border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-orange-500 font-mono"
              />
              <button
                type="button"
                onClick={() => setShowGrokKey(!showGrokKey)}
                className="absolute right-2 px-2 py-1 text-[10px] text-neutral-500 hover:text-neutral-300 cursor-pointer"
              >
                {showGrokKey ? "Hide" : "Show"}
              </button>
            </div>
          </div>
        </div>

        <div className="flex justify-end pt-2">
          <button
            type="button"
            onClick={handleSaveGrokConfig}
            disabled={isUpdating}
            className="px-4 py-2 text-xs font-medium rounded-lg bg-orange-600 hover:bg-orange-500 text-white transition-colors cursor-pointer disabled:opacity-50 flex items-center gap-1.5"
          >
            <span>Save AI Configuration</span>
          </button>
        </div>
      </section>

      {/* GitHub Outgoing Activity & Audit Log */}
      <section className="space-y-4 pt-4 border-t border-neutral-200 dark:border-neutral-800">
        <div>
          <h2 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
            <span>📜</span>
            <span>GitHub Outgoing Activity Log</span>
          </h2>
          <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
            Audit history of branches, commits, pull requests, issues, and comments created by you on GitHub.
          </p>
        </div>

        {isActivityLoading ? (
          <div className="p-6 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-900/30 text-xs text-neutral-400 animate-pulse">
            Loading activity history...
          </div>
        ) : !activityLogs || activityLogs.length === 0 ? (
          <div className="p-8 rounded-xl border border-dashed border-neutral-200 dark:border-neutral-800 text-center text-xs text-neutral-500">
            No outgoing GitHub activity recorded yet.
          </div>
        ) : (
          <div className="rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900/50 divide-y divide-neutral-100 dark:divide-neutral-800 overflow-hidden text-xs">
            {activityLogs.map((item) => (
              <div key={item.id} className="p-3.5 flex items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <span
                    className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded ${
                      item.action === "push"
                        ? "bg-purple-500/10 text-purple-400 border border-purple-500/20"
                        : item.action === "issue_create" || item.action === "issue"
                        ? "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                        : "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                    }`}
                  >
                    {item.action.replace("_", " ")}
                  </span>

                  <div>
                    <div className="font-medium text-neutral-800 dark:text-neutral-200 flex items-center gap-2">
                      {item.target_url ? (
                        <a
                          href={item.target_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-orange-500 hover:text-orange-400 underline flex items-center gap-1 font-mono text-[11px]"
                        >
                          <span>{item.target_url}</span>
                          <span>&nearr;</span>
                        </a>
                      ) : (
                        <span className="text-neutral-400 font-mono text-[11px]">
                          Action recorded
                        </span>
                      )}
                    </div>
                    <span className="text-[10px] text-neutral-400 font-mono">
                      {new Date(item.created_at).toLocaleString()}
                    </span>
                  </div>
                </div>

                <span
                  className={`text-[10px] font-semibold px-2 py-0.5 rounded ${
                    item.status === "succeeded"
                      ? "bg-emerald-500/10 text-emerald-500"
                      : item.status === "failed"
                      ? "bg-rose-500/10 text-rose-500"
                      : "bg-neutral-500/10 text-neutral-400"
                  }`}
                >
                  {item.status.toUpperCase()}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>
 
      {/* Privacy & Data Section */}
      <section className="space-y-4 pt-6 border-t border-neutral-200 dark:border-neutral-800">
        <div>
          <h2 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
            <span>🛡️</span>
            <span>Privacy & Data</span>
          </h2>
          <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
            Understand how BodhCode stores your information, which OAuth scopes are used, and exercise full control over your personal data.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Stored Data Info */}
          <div className="p-4 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900/50 space-y-3">
            <h3 className="text-xs font-semibold text-neutral-800 dark:text-neutral-200 uppercase tracking-wider">
              What Is Stored
            </h3>
            <ul className="text-xs text-neutral-600 dark:text-neutral-400 space-y-2 list-disc list-inside">
              <li><strong className="text-neutral-800 dark:text-neutral-200">Profile:</strong> GitHub login, ID, display name, avatar URL, and verified email.</li>
              <li><strong className="text-neutral-800 dark:text-neutral-200">OAuth Token:</strong> Encrypted at rest using AES-128-CBC (Fernet). Never logged, sent to browsers, or included in LLM prompts.</li>
              <li><strong className="text-neutral-800 dark:text-neutral-200">Preferences:</strong> Preferred language, UI theme, editor theme, and review mode.</li>
              <li><strong className="text-neutral-800 dark:text-neutral-200">Working Copies:</strong> In-browser file edits and unstaged changes for repositories you explore.</li>
              <li><strong className="text-neutral-800 dark:text-neutral-200">Proposals & Checkpoints:</strong> AI agent edit proposals and rollback snapshots.</li>
              <li><strong className="text-neutral-800 dark:text-neutral-200">Activity Log:</strong> Audit record of branches, commits, PRs, and issues pushed to GitHub.</li>
            </ul>
          </div>

          {/* GitHub OAuth Scopes Info */}
          <div className="p-4 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900/50 space-y-3">
            <h3 className="text-xs font-semibold text-neutral-800 dark:text-neutral-200 uppercase tracking-wider">
              OAuth Scopes & Purpose
            </h3>
            <div className="space-y-3 text-xs text-neutral-600 dark:text-neutral-400">
              <div className="p-2.5 rounded-lg bg-neutral-50 dark:bg-neutral-800/60 border border-neutral-200 dark:border-neutral-700/50">
                <div className="font-mono text-[11px] font-semibold text-neutral-800 dark:text-neutral-200">read:user, user:email</div>
                <p className="mt-1 text-[11px]">Default scope requested at sign-in. Used exclusively to authenticate your identity, retrieve your public profile, and access your primary verified email.</p>
              </div>
              <div className="p-2.5 rounded-lg bg-neutral-50 dark:bg-neutral-800/60 border border-neutral-200 dark:border-neutral-700/50">
                <div className="font-mono text-[11px] font-semibold text-neutral-800 dark:text-neutral-200">public_repo (Optional)</div>
                <p className="mt-1 text-[11px]">Requested strictly on-demand when you explicitly choose to push commits, create new branches, or open pull requests/issues on public repositories.</p>
              </div>
            </div>
          </div>
        </div>

        {/* Delete My Data (Danger Zone) */}
        <div className="p-4 rounded-xl border border-rose-200 dark:border-rose-900/50 bg-rose-50/30 dark:bg-rose-950/20 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h3 className="text-xs font-semibold text-rose-700 dark:text-rose-400 uppercase tracking-wider">
              Danger Zone: Delete My Data
            </h3>
            <p className="text-xs text-neutral-600 dark:text-neutral-400 mt-1 max-w-xl">
              Permanently delete your account, encrypted OAuth tokens, repository links, working copies, proposals, rollback checkpoints, and activity logs. Shared public repository caches remain intact.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setIsDeleteModalOpen(true)}
            className="px-4 py-2 text-xs font-medium text-white bg-rose-600 hover:bg-rose-700 active:bg-rose-800 rounded-lg shadow-sm transition-colors whitespace-nowrap self-start sm:self-auto cursor-pointer"
          >
            Delete my data
          </button>
        </div>
      </section>

      {/* Confirmation Modal */}
      {isDeleteModalOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-modal-title"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs"
        >
          <div className="bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 rounded-xl p-6 max-w-md w-full shadow-2xl space-y-4">
            <h3 id="delete-modal-title" className="text-sm font-bold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
              <span className="text-rose-500">⚠️</span>
              <span>Confirm Account & Data Deletion</span>
            </h3>
            <p className="text-xs text-neutral-600 dark:text-neutral-400 leading-relaxed">
              This action is <strong className="text-rose-500">irreversible</strong>. All your personal data, working files, proposals, and tokens will be permanently destroyed.
            </p>
            <p className="text-xs text-neutral-700 dark:text-neutral-300">
              To confirm, type <strong className="font-mono text-rose-500 font-bold select-all">DELETE</strong> below:
            </p>
            <input
              type="text"
              value={deleteConfirmationInput}
              onChange={(e) => setDeleteConfirmationInput(e.target.value)}
              placeholder="Type DELETE to confirm"
              className="w-full px-3 py-2 text-xs font-mono rounded-lg border border-neutral-300 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-950 text-neutral-900 dark:text-neutral-100 focus:outline-hidden focus:ring-2 focus:ring-rose-500"
              autoFocus
            />
            {deleteError && (
              <p className="text-xs text-rose-500 font-medium">{deleteError}</p>
            )}
            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => {
                  setIsDeleteModalOpen(false);
                  setDeleteConfirmationInput("");
                  setDeleteError(null);
                }}
                disabled={isDeleting}
                className="px-3.5 py-1.5 text-xs text-neutral-600 dark:text-neutral-400 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-lg transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmDelete}
                disabled={deleteConfirmationInput.trim() !== "DELETE" || isDeleting}
                className="px-4 py-1.5 text-xs font-medium text-white bg-rose-600 hover:bg-rose-700 disabled:opacity-40 disabled:cursor-not-allowed rounded-lg shadow-sm transition-colors cursor-pointer"
              >
                {isDeleting ? "Deleting..." : "Permanently Delete Data"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
