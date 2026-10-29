import { useEffect, useRef, useState } from "react";
import { Link, Outlet, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useLogout, useMe } from "../lib/auth";
import { LoginModal } from "./auth/LoginModal";
import {
  applyTheme,
  getStoredTheme,
  setStoredTheme,
  useThemeStore,
} from "../lib/theme";
import type { ThemePref } from "../lib/theme";

export function Layout() {
  const { data: user, isLoading } = useMe();
  const logout = useLogout();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();

  const [menuOpen, setMenuOpen] = useState(false);
  const [isLoginModalOpen, setIsLoginModalOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const resolvedTheme = useThemeStore((s) => s.resolved);

  // Sync theme on initial layout mount and on user changes
  useEffect(() => {
    if (user?.theme) {
      const serverTheme = user.theme as ThemePref;
      setStoredTheme(serverTheme);
      applyTheme(serverTheme);
    } else {
      const localTheme = getStoredTheme();
      applyTheme(localTheme);
    }
  }, [user?.theme]);

  const handleToggleTheme = () => {
    // For signed-out visitors (or instant toggle): cycles light/dark locally
    const current = resolvedTheme;
    const next: ThemePref = current === "dark" ? "light" : "dark";
    setStoredTheme(next);
    applyTheme(next);
  };

  const authError = searchParams.get("auth_error");
  const authRequired =
    searchParams.get("auth_required") === "1" ||
    (location.state as { notice?: string } | null)?.notice;

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleDismissAuthError = () => {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.delete("auth_error");
    setSearchParams(nextParams, { replace: true });
  };

  const handleDismissAuthNotice = () => {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.delete("auth_required");
    setSearchParams(nextParams, { replace: true });
    if (location.state) {
      navigate(location.pathname, { replace: true, state: {} });
    }
  };

  const handleLogout = async () => {
    setMenuOpen(false);
    await logout();
    navigate("/");
  };

  return (
    <div className="min-h-screen bg-neutral-50 dark:bg-neutral-950 text-neutral-900 dark:text-neutral-100 flex flex-col font-sans transition-colors duration-150">
      <header className="border-b border-neutral-200 dark:border-neutral-800 bg-white/80 dark:bg-neutral-900/80 backdrop-blur px-6 py-4 flex items-center justify-between sticky top-0 z-50 transition-colors duration-150">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-3">
            <Link
              to="/"
              aria-label="BodhCode Home"
              className="flex items-center gap-2.5 text-xl font-bold tracking-tight hover:opacity-90 transition-opacity focus:outline-none focus:ring-2 focus:ring-orange-500/50 rounded-lg p-0.5"
            >
              <img
                src="/logo.png"
                alt="BodhCode Logo"
                className="h-8 w-8 object-contain drop-shadow-[0_0_12px_rgba(249,115,22,0.35)] hover:scale-105 transition-transform"
              />
              <span className="bg-gradient-to-r from-orange-400 to-amber-300 bg-clip-text text-transparent font-bold tracking-tight">
                BodhCode
              </span>
            </Link>
            <span className="text-xs px-2 py-0.5 rounded-full bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400 border border-neutral-200 dark:border-neutral-700 font-mono">
              v0.1.0-alpha
            </span>
          </div>

          {user && (
            <nav className="hidden sm:flex items-center gap-1.5 text-xs font-medium">
              <Link
                to="/editor"
                id="nav-editor-link"
                className="px-3 py-1.5 rounded-lg bg-orange-500/10 hover:bg-orange-500/20 text-orange-400 border border-orange-500/30 flex items-center gap-1.5 transition-colors"
              >
                <span>💻</span>
                <span>Code Editor</span>
              </Link>
              <Link
                to="/"
                id="nav-repos-link"
                className="px-3 py-1.5 rounded-lg text-neutral-400 hover:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors flex items-center gap-1.5"
              >
                <span>🗺️</span>
                <span>Repositories</span>
              </Link>
            </nav>
          )}
        </div>

        <div id="header-actions" className="flex items-center gap-3">
          {/* Header Theme Toggle (works for signed-out visitors and signed-in users) */}
          <button
            id="header-theme-toggle"
            type="button"
            onClick={handleToggleTheme}
            aria-label="Toggle light and dark theme"
            title={`Switch to ${resolvedTheme === "dark" ? "light" : "dark"} mode`}
            className="p-2 rounded-lg text-neutral-600 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800 border border-neutral-200 dark:border-neutral-800 transition-colors cursor-pointer"
          >
            {resolvedTheme === "dark" ? (
              <svg className="w-4 h-4 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"
                />
              </svg>
            ) : (
              <svg className="w-4 h-4 text-neutral-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"
                />
              </svg>
            )}
          </button>

          {isLoading ? (
            <div className="w-8 h-8 rounded-full bg-neutral-200 dark:bg-neutral-800 animate-pulse" />
          ) : user ? (
            <div className="relative" ref={menuRef}>
              <button
                id="user-menu-btn"
                onClick={() => setMenuOpen((prev) => !prev)}
                className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-white dark:bg-neutral-900 hover:bg-neutral-100 dark:hover:bg-neutral-800 border border-neutral-200 dark:border-neutral-800 text-neutral-900 dark:text-neutral-200 transition-colors focus:outline-none focus:ring-2 focus:ring-orange-500/50 cursor-pointer"
                aria-expanded={menuOpen}
                aria-haspopup="true"
              >
                <img
                  src={user.avatar_url}
                  alt={user.login}
                  className="w-6 h-6 rounded-full border border-neutral-300 dark:border-neutral-700 object-cover"
                />
                <span className="text-sm font-medium">{user.login}</span>
                <svg
                  className={`w-3.5 h-3.5 text-neutral-400 transition-transform ${menuOpen ? "rotate-180" : ""}`}
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              {menuOpen && (
                <div
                  id="user-menu-dropdown"
                  className="absolute right-0 mt-2 w-48 py-1.5 bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 rounded-lg shadow-xl z-50 backdrop-blur"
                >
                  <div className="px-3 py-2 border-b border-neutral-200 dark:border-neutral-800/80 text-xs">
                    <p className="text-neutral-500 dark:text-neutral-400 font-medium">Signed in as</p>
                    <p className="text-neutral-900 dark:text-neutral-200 font-semibold truncate">{user.login}</p>
                  </div>
                  <Link
                    to="/settings"
                    onClick={() => setMenuOpen(false)}
                    className="block px-3 py-2 text-sm text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800 hover:text-neutral-900 dark:hover:text-neutral-100 transition-colors"
                  >
                    Settings
                  </Link>
                  <button
                    id="logout-btn"
                    onClick={handleLogout}
                    className="w-full text-left px-3 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/40 hover:text-red-700 dark:hover:text-red-300 transition-colors cursor-pointer"
                  >
                    Logout
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <button
                type="button"
                id="header-chatgpt-login-btn"
                onClick={() => setIsLoginModalOpen(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-neutral-100 dark:bg-neutral-800 hover:bg-neutral-200 dark:hover:bg-neutral-700 text-neutral-800 dark:text-neutral-200 border border-neutral-300 dark:border-neutral-700 text-xs font-semibold transition-all hover:scale-[1.02] cursor-pointer"
              >
                <span>⚡</span>
                <span>ChatGPT / Codex</span>
              </button>
              <button
                type="button"
                id="github-login-btn"
                onClick={() => setIsLoginModalOpen(true)}
                className="flex items-center gap-2 px-3.5 py-1.5 rounded-lg bg-orange-500 hover:bg-orange-600 text-white text-xs font-semibold transition-all shadow-md shadow-orange-500/20 hover:scale-[1.02] active:scale-[0.98] cursor-pointer"
              >
                <svg className="w-3.5 h-3.5 fill-current" viewBox="0 0 24 24">
                  <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
                </svg>
                <span>Login with GitHub</span>
              </button>
            </div>
          )}
        </div>
      </header>

      <main className="flex-1 max-w-6xl w-full mx-auto px-6 py-8">
        {authError && (
          <div
            id="auth-error-banner"
            className="mb-6 p-4 rounded-lg bg-red-950/40 border border-red-800/60 text-red-200 flex items-center justify-between shadow-lg"
          >
            <div className="flex items-center gap-3">
              <svg className="w-5 h-5 text-red-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span className="text-sm">
                GitHub authorization was cancelled or failed. Please try signing in again.
              </span>
            </div>
            <button
              onClick={handleDismissAuthError}
              aria-label="Dismiss auth error"
              className="text-red-400 hover:text-red-200 p-1 rounded hover:bg-red-900/40 transition-colors"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}

        {authRequired && (
          <div
            id="auth-required-banner"
            className="mb-6 p-4 rounded-lg bg-amber-950/40 border border-amber-800/60 text-amber-200 flex items-center justify-between shadow-lg"
          >
            <div className="flex items-center gap-3">
              <svg className="w-5 h-5 text-amber-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span className="text-sm">
                Sign in to continue. You must be signed in with GitHub to access that page.
              </span>
            </div>
            <button
              onClick={handleDismissAuthNotice}
              aria-label="Dismiss auth notice"
              className="text-amber-400 hover:text-amber-200 p-1 rounded hover:bg-amber-900/40 transition-colors"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}

        <Outlet />
      <LoginModal isOpen={isLoginModalOpen} onClose={() => setIsLoginModalOpen(false)} />
      </main>

      <footer className="border-t border-neutral-200 dark:border-neutral-800 py-4 text-center text-xs text-neutral-500">
        BodhCode &copy; {new Date().getFullYear()} &mdash; Interactive Repository Dependency Mapping
      </footer>
    </div>
  );
}
