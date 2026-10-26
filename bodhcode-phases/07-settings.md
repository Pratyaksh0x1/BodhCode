# Phase 7 — Settings: language and theme

**Goal.** A person chooses the language they want BodhCode to show repo content in, picks light / dark / follow-system for the app, and picks an editor theme. The choices are saved to their account, applied before first paint (no flash of the wrong theme), and available to every later phase through one place.

## Aapko karna hai (before you paste the prompt)

- [ ] Phase 2 pass ho chuka hai (users table + login). Phase 6 ke baad karna zaroori nahi, par agar ho chuka hai to theme canvas par bhi dikhega.
- [ ] `git checkout -b phase-7`.
- [ ] Test ke liye OS ka theme (light/dark) badalna aana chahiye.

## Build

### Data model (migration)
Add to `User`: `editor_theme` (string, default `"auto"`, allowed `auto | vs | vs-dark | hc-black | hc-light`). `preferred_language` and `theme` already exist from Phase 2. Existing rows get defaults; the migration must be reversible.

### Language catalogue (`app/i18n/languages.py`)
A constant list of supported languages with `code` (ISO 639-1), `english_name`, `native_name`, and `rtl: bool`. Include at least: `en, hi, bn, ta, te, mr, ur, ja, zh, ko, es, fr, de, pt, ru, uk, ar, fa, he, it, tr, id, vi, th, pl, nl, sv, cs, ro, el, hu`. Helpers: `is_supported(code)`, `get_language(code)`. `GET /meta/languages` (public, cacheable) returns the list.

### Settings API (`app/routes/settings.py`)
- `PATCH /auth/me/settings` with a pydantic model where every field is optional: `preferred_language`, `theme` (`system | light | dark`), `editor_theme`. Unknown fields rejected (`extra="forbid"`). Invalid values → 422 with a clear message.
- Returns the updated public user object (same shape as `/auth/me`, now including `editor_theme`).
- Update `/auth/me` to include `editor_theme`.
- Structure the settings model so later phases can add fields (review mode, auto-use skills) without a rewrite: one `UserSettings` pydantic model, one update function, one place where validation lives.
- Requires auth and the CSRF header from Phase 2.

### Frontend: theme mechanism
- `src/lib/theme.ts`:
  - `type ThemePref = "system" | "light" | "dark"`.
  - `resolveTheme(pref, systemIsDark): "light" | "dark"`.
  - `applyTheme(pref)`: toggles the `dark` class on `document.documentElement` and sets `color-scheme`.
  - When `pref === "system"`, subscribe to `matchMedia("(prefers-color-scheme: dark)")` changes and update live; unsubscribe when the pref changes.
  - `localStorage` key `bodhcode.theme` stores the pref for instant startup, wrapped in `try/catch`.
- **No flash:** a tiny inline `<script>` in `index.html` (before the app bundle) reads `localStorage["bodhcode.theme"]`, resolves it, and sets the `dark` class synchronously.
- On sign-in, the server value from `/auth/me` wins and is written back to `localStorage`.
- Editor theme helper `resolveEditorTheme(editorPref, appResolvedTheme)`: `auto` → `vs-dark` / `vs` following the app theme; otherwise the explicit choice.

### Frontend: Settings page (`/settings`, protected)
Sections:
1. **Language** — a searchable combobox listing `日本語 · Japanese` style labels (native + English), the current choice marked, a short explanation: "Repos in other languages — README, issues, pull requests — will be shown in this language." Right-to-left languages show a small note.
2. **Appearance** — segmented control: System / Light / Dark with live preview of the change.
3. **Editor theme** — select: Auto (follow app theme), Light, Dark, High contrast dark, High contrast light. A small preview block shows a code sample in the chosen theme (use a static styled `<pre>`; the real editor arrives in Phase 11).
- Changes save immediately with an **optimistic update** (react-query mutation) and a subtle "Saved" confirmation; on error, roll back and show the message.
- `useSettings()` hook exposes the current values from `useMe()`; a small zustand slice mirrors theme so non-React code (the future Monaco setup) can read it.
- Signed-out visitors can still toggle theme from a header control (stored in `localStorage` only, never the server).

### Tests
Backend: valid update persists; each invalid value → 422; unknown field → 422; user A's update does not touch user B; unauthenticated → 401; missing CSRF header → 403; `/meta/languages` returns the catalogue with required keys; every code in the list is unique and two letters.
Frontend (vitest): `resolveTheme` truth table; `resolveEditorTheme` table; `applyTheme` toggles the class; the system-change listener updates and is cleaned up.

## Constraints

- **One source of truth per user:** the server value (after sign-in) wins; `localStorage` is only a cache for first paint.
- The `dark` class on `<html>` is the only mechanism for app theming — all colors are tokens that key off it. No component sets its own colors based on `matchMedia`.
- `try/catch` around every `localStorage` access (it can throw or be empty).
- Language codes are validated **server-side** against the catalogue; the client list is display-only.
- Do not translate the BodhCode UI itself in this phase — `preferred_language` controls repo content only.
- No LLM call in this phase.

## Order of work

1. Migration + `languages.py` + `/meta/languages` + tests.
2. Settings model, `PATCH` route, `/auth/me` update + tests.
3. `theme.ts` + inline script + tests.
4. Settings page with the three sections.
5. Header theme toggle for signed-out visitors.
6. Cross-check: reload, sign out/in, OS theme change.

## Acceptance check

1. Open Settings, choose Japanese → "Saved" appears; reload; still Japanese. `GET /auth/me` shows `preferred_language: "ja"`.
2. Choose Dark → page turns dark immediately; reload with throttled CPU in devtools: **no light flash** before dark appears.
3. Choose System while the OS is dark → dark; switch the OS to light → the app switches live without a reload.
4. Choose Light while the OS is dark → the app stays light (forced light wins).
5. Set editor theme to "High contrast dark" → the preview block changes; `GET /auth/me` returns `editor_theme: "hc-black"`.
6. Send `PATCH` with `{"preferred_language": "xx"}` → 422 with a readable message; the UI shows an error and reverts.
7. Sign in on a second browser: the saved preferences load there too.
8. Sign out: the header toggle still switches theme and persists locally; signing in again applies the server's saved theme.
9. All tests, `ruff`, `pnpm lint`, `pnpm build` pass.

## Not in this phase

Translating repo content (Phase 9). Using `preferred_language` anywhere other than saving it. The real Monaco editor (Phase 11). Review mode and skills settings (Phases 12–13). Translating BodhCode's own interface strings.

## Paste this to the agent

```text
Read AGENTS.md, then this entire file (07-settings.md).
Implement exactly "Build", obey "Constraints", follow "Order of work".
Do not implement anything under "Not in this phase".
Finish by running the Acceptance check, report PASS / FAIL / NEEDS MANUAL TEST per item, list commands I must run, then stop.
```
