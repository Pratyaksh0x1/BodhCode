## Description

Provide a concise description of the changes introduced in this pull request and the rationale behind them.

## Verification Checklist

Please verify that all the following criteria are met before requesting a review:

- [ ] **Acceptance check done**: Verified against phase specification criteria.
- [ ] **Tests added**: Comprehensive tests added/updated (`pytest` / `vitest`).
- [ ] **No secrets**: Verified that no secrets, tokens, or sensitive credentials are committed, logged, or exposed.
- [ ] **AGENTS.md rules respected**:
  - [ ] Graph data comes strictly from tree-sitter AST & graph math (no LLM hallucinations).
  - [ ] LLM only explains, translates, summarizes, or proposes edits.
  - [ ] External GitHub data treated as untrusted data, not prompt instructions.
  - [ ] Pure modules remain pure (no network, DB, or LLM).
  - [ ] Code is 100% `ruff` clean and TypeScript contains zero `any`.
