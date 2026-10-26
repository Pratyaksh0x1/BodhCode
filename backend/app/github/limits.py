"""Limits, thresholds, and allowed patterns for GitHub repository ingestion."""

from typing import Final

MAX_REPO_KB: Final[int] = 200_000  # 200 MB max default_branch_size_kb from GitHub API
MAX_SOURCE_FILES: Final[int] = 5000  # Max extracted source code files per repository
MAX_FILE_BYTES: Final[int] = 1_000_000  # 1 MB max size per individual source file
MAX_UNCOMPRESSED_BYTES: Final[int] = 500_000_000  # 500 MB zip-bomb defense threshold
INGEST_VERSION: Final[int] = 1  # Ingest pipeline format version marker

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


def is_allowed_file(file_name: str) -> bool:
    """Check if file should be retained during archive extraction.

    Allows TypeScript/JavaScript source files, package manifests, TypeScript configs,
    and README files.
    """
    lower = file_name.lower()
    # Check compound extension first (.d.ts)
    if lower.endswith(".d.ts"):
        return True

    # Check extension
    for ext in ALLOWED_EXTENSIONS:
        if lower.endswith(ext):
            return True

    # Check specific config files and README patterns
    if lower == "package.json" or lower == "jsconfig.json":
        return True
    if lower.startswith("tsconfig") and lower.endswith(".json"):
        return True
    if lower == "readme" or lower.startswith("readme.") or lower.startswith("readme-"):
        return True

    return False
