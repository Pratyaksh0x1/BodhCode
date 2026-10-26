import { Link, Outlet } from "react-router-dom";

export function Layout() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur px-6 py-4 flex items-center justify-between sticky top-0 z-50">
        <div className="flex items-center gap-3">
          <Link
            to="/"
            className="text-xl font-bold tracking-tight bg-gradient-to-r from-sky-400 to-indigo-400 bg-clip-text text-transparent hover:opacity-90 transition-opacity"
          >
            BodhCode
          </Link>
          <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700 font-mono">
            v0.1.0-alpha
          </span>
        </div>
        {/* Right header slot reserved for future auth / user profile in later phases */}
        <div id="header-actions" className="flex items-center gap-4">
          <Link
            to="/settings"
            className="text-sm text-slate-400 hover:text-slate-200 transition-colors"
          >
            Settings
          </Link>
        </div>
      </header>

      <main className="flex-1 max-w-6xl w-full mx-auto px-6 py-8">
        <Outlet />
      </main>

      <footer className="border-t border-slate-900 py-4 text-center text-xs text-slate-500">
        BodhCode &copy; {new Date().getFullYear()} &mdash; Interactive Repository Dependency Mapping
      </footer>
    </div>
  );
}
