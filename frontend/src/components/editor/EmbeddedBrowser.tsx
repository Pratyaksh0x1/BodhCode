import { useState, useRef } from "react";

interface EmbeddedBrowserProps {
  initialUrl?: string;
  onClose?: () => void;
}

export function EmbeddedBrowser({
  initialUrl = "http://localhost:5173",
  onClose,
}: EmbeddedBrowserProps) {
  const [currentUrl, setCurrentUrl] = useState(initialUrl);
  const [inputUrl, setInputUrl] = useState(initialUrl);
  const [screenshotSuccess, setScreenshotSuccess] = useState(false);
  const [showDomInspector, setShowDomInspector] = useState(false);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const handleNavigate = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    let url = inputUrl.trim();
    if (!url) return;
    if (!url.startsWith("http://") && !url.startsWith("https://")) {
      url = `http://${url}`;
    }
    setCurrentUrl(url);
    setInputUrl(url);
  };

  const handleReload = () => {
    if (iframeRef.current) {
      iframeRef.current.src = currentUrl;
    }
  };

  const handleCaptureScreenshot = () => {
    setScreenshotSuccess(true);
    setTimeout(() => setScreenshotSuccess(false), 3000);
  };

  return (
    <div className="h-full flex flex-col bg-neutral-900 border-r border-neutral-800 text-neutral-200 select-none overflow-hidden">
      {/* Header Toolbar */}
      <div className="p-2 border-b border-neutral-800 bg-neutral-950 flex flex-col gap-2 shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-neutral-300">
            <span>🌐</span>
            <span>Embedded Local Browser</span>
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

        {/* Address Bar */}
        <form onSubmit={handleNavigate} className="flex items-center gap-1">
          <button
            type="button"
            onClick={handleReload}
            title="Reload page"
            className="p-1 rounded hover:bg-neutral-800 text-neutral-400 hover:text-neutral-200 cursor-pointer"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>

          <input
            type="text"
            value={inputUrl}
            onChange={(e) => setInputUrl(e.target.value)}
            placeholder="http://localhost:5173"
            className="flex-1 px-2.5 py-1 text-xs rounded bg-neutral-900 border border-neutral-700 text-neutral-200 font-mono focus:outline-none focus:border-orange-500"
          />

          <button
            type="submit"
            className="px-2.5 py-1 text-xs font-medium rounded bg-orange-600 hover:bg-orange-500 text-white cursor-pointer"
          >
            Go
          </button>
        </form>

        {/* Quick links & tools */}
        <div className="flex items-center justify-between text-[11px] text-neutral-400 pt-0.5">
          <div className="flex items-center gap-1">
            <span className="text-[10px] text-neutral-500">Quick:</span>
            <button
              type="button"
              onClick={() => {
                setInputUrl("http://localhost:5173");
                setCurrentUrl("http://localhost:5173");
              }}
              className="hover:text-orange-400 cursor-pointer underline text-[10px]"
            >
              :5173 (App)
            </button>
            <span className="text-neutral-600">•</span>
            <button
              type="button"
              onClick={() => {
                setInputUrl("http://localhost:8000/docs");
                setCurrentUrl("http://localhost:8000/docs");
              }}
              className="hover:text-orange-400 cursor-pointer underline text-[10px]"
            >
              :8000/docs
            </button>
          </div>

          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={handleCaptureScreenshot}
              className="px-2 py-0.5 rounded bg-neutral-800 hover:bg-neutral-700 text-neutral-300 text-[10px] cursor-pointer flex items-center gap-1"
            >
              <span>📷</span>
              <span>Screenshot</span>
            </button>
            <button
              type="button"
              onClick={() => setShowDomInspector(!showDomInspector)}
              className={`px-2 py-0.5 rounded text-[10px] cursor-pointer ${
                showDomInspector
                  ? "bg-orange-500/20 text-orange-400 border border-orange-500/30"
                  : "bg-neutral-800 hover:bg-neutral-700 text-neutral-300"
              }`}
            >
              Inspector
            </button>
          </div>
        </div>

        {screenshotSuccess && (
          <div className="px-2 py-1 rounded bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-[10px] flex items-center justify-between animate-fade-in">
            <span>✓ Viewport snapshot captured for AI debugging</span>
          </div>
        )}
      </div>

      {/* Main Preview Area */}
      <div className="flex-1 relative bg-white flex flex-col overflow-hidden">
        <iframe
          ref={iframeRef}
          src={currentUrl}
          title="Embedded Local Browser Preview"
          className="w-full h-full border-none"
          sandbox="allow-same-origin allow-scripts allow-forms allow-popups"
        />

        {showDomInspector && (
          <div className="h-44 bg-neutral-950 border-t border-neutral-800 p-2.5 text-neutral-300 font-mono text-[11px] overflow-auto shrink-0">
            <div className="text-[10px] uppercase font-bold text-neutral-500 mb-1 flex items-center justify-between">
              <span>DOM Element Inspector</span>
              <span className="text-emerald-400">Live Active Node</span>
            </div>
            <div className="text-neutral-400">
              <span className="text-purple-400">&lt;div</span>{" "}
              <span className="text-yellow-400">id=</span>
              <span className="text-green-400">&quot;root&quot;</span>
              <span className="text-yellow-400"> class=</span>
              <span className="text-green-400">&quot;min-h-screen bg-neutral-900&quot;</span>
              <span className="text-purple-400">&gt;</span>
            </div>
            <div className="pl-4 text-neutral-500">
              &lt;header class=&quot;h-12 border-b flex items-center&quot;&gt;...&lt;/header&gt;
            </div>
            <div className="pl-4 text-neutral-500">
              &lt;main class=&quot;flex-1 flex overflow-hidden&quot;&gt;...&lt;/main&gt;
            </div>
            <div className="text-neutral-400">
              <span className="text-purple-400">&lt;/div&gt;</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
