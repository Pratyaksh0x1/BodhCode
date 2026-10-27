import { useEffect, useMemo, useRef, useState } from "react";
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

  // Searchable language combobox state
  const [langSearch, setLangSearch] = useState("");
  const [langDropdownOpen, setLangDropdownOpen] = useState(false);
  const langDropdownRef = useRef<HTMLDivElement>(null);

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
    </div>
  );
}
