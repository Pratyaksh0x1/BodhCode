"""Limits, thresholds, and allowed patterns for GitHub repository ingestion."""

from typing import Final

MAX_REPO_KB: Final[int] = 200_000  # 200 MB max default_branch_size_kb from GitHub API
MAX_SOURCE_FILES: Final[int] = 5000  # Max extracted source code files per repository
MAX_FILE_BYTES: Final[int] = 1_000_000  # 1 MB max size per individual source file
MAX_UNCOMPRESSED_BYTES: Final[int] = 500_000_000  # 500 MB zip-bomb defense threshold
INGEST_VERSION: Final[int] = 2  # Ingest pipeline format version marker

ALLOWED_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".mts",
        ".cts",
        ".d.ts",
    }
)

EDITABLE_TEXT_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {
        ".md",
        ".mdx",
        ".css",
        ".scss",
        ".html",
        ".yml",
        ".yaml",
        ".toml",
        ".txt",
        ".json",
        ".svg",
    }
)

ALL_ALLOWED_EXTENSIONS: Final[frozenset[str]] = ALLOWED_EXTENSIONS | EDITABLE_TEXT_EXTENSIONS

EXCLUDED_DIRECTORIES: Final[frozenset[str]] = frozenset(
    {
        "node_modules",
        ".git",
        "dist",
        "build",
        ".next",
        "coverage",
        "vendor",
    }
)

LOCK_FILES: Final[frozenset[str]] = frozenset(
    {
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "bun.lockb",
        "composer.lock",
        "cargo.lock",
        "poetry.lock",
        "gemfile.lock",
    }
)

KEY_EXTENSIONS: Final[tuple[str, ...]] = (
    ".key",
    ".pem",
    ".crt",
    ".cer",
    ".pfx",
    ".p12",
    ".pub",
)


def is_allowed_file(file_name: str) -> bool:
    """Check if file should be retained during archive extraction.

    Allows TypeScript/JavaScript source files, configs, manifests, README files,
    and editable text files (.md, .json, .css, etc.), while strictly disallowing
    .env*, key files, lock files, and binaries.
    """
    lower = file_name.lower()

    # 1. Block .env* files
    if lower == ".env" or lower.startswith(".env.") or lower.startswith(".env_"):
        return False

    # 2. Block lock files
    if lower.endswith(".lock") or lower in LOCK_FILES:
        return False

    # 3. Block key / certificate files
    if lower.endswith(KEY_EXTENSIONS) or any(
        k in lower for k in ("id_rsa", "id_ed25519", "id_dsa", "id_ecdsa")
    ):
        return False

    # 4. Check compound extension first (.d.ts)
    if lower.endswith(".d.ts"):
        return True

    # 5. Check allowed extensions
    for ext in ALL_ALLOWED_EXTENSIONS:
        if lower.endswith(ext):
            return True

    # 6. Check specific README patterns
    if lower == "readme" or lower.startswith("readme.") or lower.startswith("readme-"):
        return True

    return False
