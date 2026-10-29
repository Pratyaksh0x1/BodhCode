import { useState } from "react";

interface Extension {
  id: string;
  name: string;
  description: string;
  author: string;
  version: string;
  enabled: boolean;
  category: "ai" | "linter" | "language" | "tools";
  icon: string;
}

const DEFAULT_EXTENSIONS: Extension[] = [
  {
    id: "bodhcode-ast",
    name: "BodhCode AST Graph Engine",
    description: "Pure Tree-Sitter deterministic code parsing & dependency math.",
    author: "BodhCode Team",
    version: "1.0.0",
    enabled: true,
    category: "tools",
    icon: "🗺️",
  },
  {
    id: "chatgpt-codex",
    name: "OpenAI Codex & ChatGPT Agent",
    description: "In-browser project synthesis and multi-file code editing via ChatGPT.",
    author: "OpenAI & BodhCode",
    version: "2.4.0",
    enabled: true,
    category: "ai",
    icon: "⚡",
  },
  {
    id: "github-copilot",
    name: "GitHub Copilot",
    description: "AI pair programmer and code completion powered by GitHub account.",
    author: "GitHub",
    version: "1.145.0",
    enabled: true,
    category: "ai",
    icon: "🐙",
  },
  {
    id: "grok-agent",
    name: "Grok 120B Code Assistant",
    description: "Ultra-fast code review and multi-agent blast radius reasoning.",
    author: "xAI",
    version: "1.2.0",
    enabled: true,
    category: "ai",
    icon: "🧠",
  },
  {
    id: "prettier",
    name: "Prettier - Code Formatter",
    description: "Consistent code styling for JavaScript, TypeScript, CSS, and HTML.",
    author: "Prettier",
    version: "3.2.5",
    enabled: true,
    category: "linter",
    icon: "✨",
  },
  {
    id: "eslint",
    name: "ESLint Strict",
    description: "Integrates ESLint into BodhCode editor with zero-any enforcement.",
    author: "OpenJS Foundation",
    version: "9.1.0",
    enabled: true,
    category: "linter",
    icon: "🛡️",
  },
  {
    id: "tailwind-intellisense",
    name: "Tailwind CSS v4 IntelliSense",
    description: "Intelligent Tailwind CSS completions, syntax highlighting, and linting.",
    author: "Tailwind Labs",
    version: "0.10.5",
    enabled: true,
    category: "language",
    icon: "🎨",
  },
  {
    id: "python-tooling",
    name: "Python Language Support",
    description: "Rich support for Python with linting (Ruff), debugging, and type checking.",
    author: "Microsoft",
    version: "2026.2.0",
    enabled: true,
    category: "language",
    icon: "🐍",
  },
];

export function ExtensionsSidebar() {
  const [extensions, setExtensions] = useState<Extension[]>(DEFAULT_EXTENSIONS);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterCategory, setFilterCategory] = useState<string>("all");

  const toggleExtension = (id: string) => {
    setExtensions((prev) =>
      prev.map((ext) => (ext.id === id ? { ...ext, enabled: !ext.enabled } : ext))
    );
  };

  const filteredExtensions = extensions.filter((ext) => {
    const matchesSearch =
      ext.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      ext.description.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesCategory = filterCategory === "all" || ext.category === filterCategory;
    return matchesSearch && matchesCategory;
  });

  return (
    <div className="w-80 bg-neutral-900 border-r border-neutral-800 flex flex-col h-full text-xs text-neutral-300 overflow-hidden select-none">
      {/* Header */}
      <div className="px-4 py-3 border-b border-neutral-800 bg-neutral-900/90 shrink-0 space-y-2.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-orange-400 font-bold">🧩</span>
            <span className="font-semibold uppercase tracking-wider text-[11px] text-neutral-200">
              Extensions
            </span>
          </div>
          <span className="text-[10px] text-neutral-500 font-mono">
            {extensions.filter((e) => e.enabled).length} Enabled
          </span>
        </div>

        <input
          type="text"
          placeholder="Search Extensions in Marketplace..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full px-2.5 py-1.5 rounded-lg bg-neutral-950 border border-neutral-800 text-neutral-200 placeholder-neutral-600 focus:outline-none focus:border-orange-500 text-[11px]"
        />

        {/* Categories */}
        <div className="flex items-center gap-1 overflow-x-auto text-[10px]">
          {["all", "ai", "linter", "language", "tools"].map((cat) => (
            <button
              key={cat}
              type="button"
              onClick={() => setFilterCategory(cat)}
              className={`px-2 py-0.5 rounded capitalize transition-colors cursor-pointer ${
                filterCategory === cat
                  ? "bg-neutral-800 text-orange-400 font-semibold"
                  : "text-neutral-500 hover:text-neutral-300"
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      {/* Extensions List */}
      <div className="flex-1 overflow-y-auto divide-y divide-neutral-850 p-2 space-y-1">
        {filteredExtensions.map((ext) => (
          <div
            key={ext.id}
            className="p-2.5 rounded-xl hover:bg-neutral-850/50 transition-colors space-y-1.5"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="text-base shrink-0">{ext.icon}</span>
                <div>
                  <h4 className="font-semibold text-neutral-200 text-[11px] leading-tight">
                    {ext.name}
                  </h4>
                  <p className="text-[10px] text-neutral-500">
                    {ext.author} &bull; v{ext.version}
                  </p>
                </div>
              </div>

              <button
                type="button"
                onClick={() => toggleExtension(ext.id)}
                className={`px-2 py-0.5 rounded text-[10px] font-semibold transition-all cursor-pointer ${
                  ext.enabled
                    ? "bg-emerald-950/60 text-emerald-400 border border-emerald-800/60 hover:bg-emerald-900/60"
                    : "bg-neutral-800 text-neutral-400 hover:bg-neutral-700"
                }`}
              >
                {ext.enabled ? "Enabled" : "Disabled"}
              </button>
            </div>

            <p className="text-[11px] text-neutral-400 leading-relaxed">{ext.description}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
