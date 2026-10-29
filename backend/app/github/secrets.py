"""Pure secret scanner for repository changes.

Blocks paths and contents matching sensitive tokens, keys, and workflow files
before pushing to GitHub. Crucially, secret values are NEVER echoed or logged.
"""

import fnmatch
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

# Blocked filename patterns (checked against file basename)
BLOCKED_FILENAME_PATTERNS: tuple[tuple[str, str, str], ...] = (
    (".env*", "env_file", "Environment variable file (.env*) blocked."),
    ("*.pem", "pem_file", "PEM certificate or key file (*.pem) blocked."),
    ("id_rsa*", "ssh_key_file", "SSH private key file (id_rsa*) blocked."),
    ("*.key", "key_file", "Private key file (*.key) blocked."),
    ("credentials*", "credentials_file", "Credentials file (credentials*) blocked."),
)

# Content regular expressions: (compiled regex, pattern_name, human message)
CONTENT_PATTERNS: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "aws_access_key",
        "AWS Access Key ID detected in file content.",
    ),
    (
        re.compile(r"\b(ghp|gho|ghu|ghs|ghr|github_pat)_[a-zA-Z0-9_]{20,}\b"),
        "github_token",
        "GitHub personal access token detected in file content.",
    ),
    (
        re.compile(r"\bgsk_[a-zA-Z0-9]{20,}\b"),
        "groq_api_key",
        "Groq API key detected in file content.",
    ),
    (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        "private_key",
        "Private key header detected in file content.",
    ),
    (
        re.compile(r"(?i)\bapi[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}['\"]?"),
        "generic_api_key",
        "Generic API key assignment detected in file content.",
    ),
)


@dataclass(frozen=True)
class SecretFinding:
    """Detected sensitive file or pattern in outgoing changes.

    The actual secret value is never stored or echoed here.
    """

    path: str
    pattern_name: str
    message: str


def scan_file(path: str, content: str | None = None) -> list[SecretFinding]:
    """Scan a single path and its optional text content for secrets and restricted files."""
    findings: list[SecretFinding] = []
    clean_path = path.replace("\\", "/").strip("/")
    pure_p = PurePosixPath(clean_path)
    filename = pure_p.name.lower()

    # 1. Check for GitHub Actions workflow directory
    if clean_path.startswith(".github/workflows/") or "/.github/workflows/" in clean_path:
        findings.append(
            SecretFinding(
                path=clean_path,
                pattern_name="github_workflow",
                message=(
                    "GitHub Actions workflow files require additional permissions "
                    "and cannot be pushed via BodhCode."
                ),
            )
        )

    # 2. Check filename against blocked patterns
    for pattern, name, msg in BLOCKED_FILENAME_PATTERNS:
        if fnmatch.fnmatch(filename, pattern):
            findings.append(
                SecretFinding(
                    path=clean_path,
                    pattern_name=name,
                    message=msg,
                )
            )

    # 3. Check text content if provided
    if content:
        for regex, name, msg in CONTENT_PATTERNS:
            if regex.search(content):
                findings.append(
                    SecretFinding(
                        path=clean_path,
                        pattern_name=name,
                        message=msg,
                    )
                )

    return findings


def scan_changes(changes: list[dict[str, Any]]) -> list[SecretFinding]:
    """Scan all items in a change set for restricted filenames and sensitive tokens."""
    findings: list[SecretFinding] = []
    for item in changes:
        path = item.get("path", "")
        # Deletions don't push new content, but we still verify path
        content = item.get("content") if item.get("status") != "deleted" else None
        file_findings = scan_file(path, content)
        findings.extend(file_findings)
    return findings
