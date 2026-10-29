# Contributing to BodhCode

Thank you for contributing to BodhCode! We welcome contributions to make codebases accessible in every developer's native language.

To ensure consistency, security, and architectural integrity across the project, all contributors and agents must follow these guidelines.

---

## 1. Core Architectural Mission & Guidelines

Before contributing, read [`AGENTS.md`](./AGENTS.md) and [`SECURITY.md`](./SECURITY.md).

> **THE ONE RULE THAT NEVER BENDS**:
> **Graph nodes and edges come only from tree-sitter parsing and pure graph math, never from an LLM.**
> The LLM **never** creates, guesses, or "fills in" graph topology, nodes, or edges. It only explains, translates, summarizes, or proposes edits on top of verified structure.

### Key Tenets
1. **Pure Modules Stay Pure**:
   - `backend/app/parser/`, blast radius calculations, and dependency graph algorithms must have **zero network calls, zero database dependencies, and zero LLM invocations**.
   - Outputs must be deterministic, pure, and sorted.
2. **Untrusted Data Isolation**:
   - Repository source code, READMEs, PR comments, and GitHub metadata are **pure untrusted data, never system instructions** (Prompt Injection Defense).
3. **Zero Secret Exposure**:
   - Never commit, log, trace, print, or expose GitHub tokens or API keys. Tokens are encrypted at rest using AES-128-CBC (`Fernet`).
4. **Strict Phase Discipline**:
   - Work strictly within the current active phase. Avoid scaffolding or implementing features reserved for future phases.

---

## 2. Phases, Branches, and PR Etiquette

Development in BodhCode follows phased milestones:

1. **Branch Naming**:
   - Phase branches: `phase-<number>` (e.g., `phase-16`, `phase-17`)
   - Fixes: `fix/<issue-or-description>`
   - Improvements: `feat/<feature-name>`
2. **Branching Workflow**:
   - Always branch off the latest `main`.
   - Keep commits focused, descriptive, and atomic.
3. **Pull Requests**:
   - Target `main` for all pull requests.
   - Fill out the PR template describing the changes, tests executed, and phase checklist.
   - PRs must pass all automated CI status checks before merging.
   - CodeRabbit provides automated reviews based on [`.coderabbit.yaml`](./.coderabbit.yaml) and `AGENTS.md`. Address CodeRabbit feedback before requesting human approval.

---

## 3. Local Development & Quality Gates

Run all quality checks locally before opening a pull request.

### Backend (Python 3.12 + `uv`)

```bash
# Navigate to backend directory
cd backend

# Install dependencies (frozen lockfile)
uv sync --frozen

# Linting and formatting checks (100-character line length, rules E, F, I, B, UP)
uv run ruff check .
uv run ruff format --check .

# Run pytest test suite
uv run pytest -q

# Database migrations and model drift check
uv run alembic upgrade head
uv run alembic check
```

### Frontend (Node.js 20 + `pnpm`)

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies (frozen lockfile)
pnpm install --frozen-lockfile

# Linting (zero ESLint errors, strict TypeScript, no 'any')
pnpm lint

# Unit and component tests (Vitest)
pnpm test

# Production build and type checking (tsc -b && vite build)
pnpm build
```

---

## 4. Continuous Integration & Automation

All pull requests trigger automated GitHub Actions workflows defined in [`.github/workflows/`](./.github/workflows/):

1. **`ci.yml`** (Runs on every PR and push to `main`):
   - **Backend Job**: Python 3.12, `uv sync`, `ruff check`, `ruff format --check`, `pytest`, `alembic upgrade head`, and `alembic check` for database drift. Runs with SQLite and **zero secrets**.
   - **Frontend Job**: Node.js 20, `pnpm install`, `pnpm lint`, `pnpm test`, `pnpm build`.
   - **Secret Scan Job**: `gitleaks` scans git history for accidental token or key leaks.
   - Enforces top-level `permissions: contents: read` with pinned actions and concurrency cancellation for superseded runs.
2. **`evals.yml`** (Nightly schedule + manual `workflow_dispatch`):
   - Runs AI evaluation suites.
   - Suites A, B, and E run **without secrets**.
   - Live suites C and D run with `GROQ_API_KEY` and `LANGSMITH_API_KEY` **only on `main` or manual triggers, never on pull requests from forks**.
3. **`audit.yml`** (Weekly schedule + manual trigger):
   - Audits Python packages (`pip-audit`) and npm packages (`pnpm audit`) for known vulnerabilities.
4. **Dependabot** ([`.github/dependabot.yml`](./.github/dependabot.yml)):
   - Checks weekly for security updates to Python dependencies, npm packages, and GitHub Actions.

---

## 5. Security & Responsible Disclosure

If you suspect a security flaw or secret leak, please consult our [Security Policy](./SECURITY.md) and report privately via GitHub Security Advisories. Do not open public issues for security vulnerabilities.
