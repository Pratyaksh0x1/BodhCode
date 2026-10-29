"""Pure tests for secret scanner and branch name validator."""

import pytest

from app.github.branch import InvalidBranchNameError, validate_branch_name
from app.github.secrets import scan_changes, scan_file


def test_validate_branch_name_valid() -> None:
    assert validate_branch_name("feature/add-login") == "feature/add-login"
    assert validate_branch_name("fix.bug-123") == "fix.bug-123"
    assert validate_branch_name("patch_1") == "patch_1"


def test_validate_branch_name_protected() -> None:
    with pytest.raises(InvalidBranchNameError) as exc:
        validate_branch_name("main")
    assert "protected branch name" in str(exc.value)

    with pytest.raises(InvalidBranchNameError) as exc:
        validate_branch_name("master")
    assert "protected branch name" in str(exc.value)


@pytest.mark.parametrize(
    "bad_branch",
    [
        "",
        "../traversal",
        "foo/../bar",
        "-leading-dash",
        "/leading-slash",
        "trailing-slash/",
        "feature.lock",
        "contains spaces",
        "contains$special!",
    ],
)
def test_validate_branch_name_invalid_patterns(bad_branch: str) -> None:
    with pytest.raises(InvalidBranchNameError):
        validate_branch_name(bad_branch)


def test_scan_file_blocked_paths() -> None:
    # Workflow file
    f_wf = scan_file(".github/workflows/ci.yml", "name: CI")
    assert len(f_wf) == 1
    assert f_wf[0].pattern_name == "github_workflow"

    # Blocked filenames
    assert scan_file(".env", "FOO=bar")[0].pattern_name == "env_file"
    assert scan_file(".env.production", "")[0].pattern_name == "env_file"
    assert scan_file("certs/server.pem", "")[0].pattern_name == "pem_file"
    assert scan_file("keys/id_rsa", "")[0].pattern_name == "ssh_key_file"
    assert scan_file("config/database.key", "")[0].pattern_name == "key_file"
    assert scan_file("credentials.json", "")[0].pattern_name == "credentials_file"


def test_scan_file_sensitive_content() -> None:
    # AWS key
    f_aws = scan_file("src/config.ts", 'const key = "AKIAIOSFODNN7EXAMPLE";')
    assert any(f.pattern_name == "aws_access_key" for f in f_aws)

    # GitHub token
    f_gh = scan_file("src/client.ts", 'token = "ghp_1234567890abcdefghijklmnopqrstuvwxyz"')
    assert any(f.pattern_name == "github_token" for f in f_gh)

    # Groq API key
    f_gsk = scan_file("src/llm.ts", 'const k = "gsk_1234567890abcdefghijklmnopqrstuvwxyz"')
    assert any(f.pattern_name == "groq_api_key" for f in f_gsk)

    # Private key header
    f_pk = scan_file("src/auth.ts", "-----BEGIN RSA PRIVATE KEY-----\nMIIEowI...")
    assert any(f.pattern_name == "private_key" for f in f_pk)

    # Generic api key
    f_gen = scan_file("src/api.ts", 'const API_KEY = "abcdef1234567890abcdef";')
    assert any(f.pattern_name == "generic_api_key" for f in f_gen)


def test_scan_changes_clean() -> None:
    changes = [
        {"path": "src/app.ts", "status": "modified", "content": "console.log('clean');"},
        {"path": "README.md", "status": "modified", "content": "# Documentation"},
    ]
    findings = scan_changes(changes)
    assert len(findings) == 0
