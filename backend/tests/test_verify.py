"""Unit tests for app/ai/verify.py."""

import pytest

from app.ai.verify import (
    annotate,
    extract_path_mentions,
    verify_mentions,
)


@pytest.fixture
def sample_graph_nodes() -> set[str]:
    """Sample repository graph node IDs."""
    return {
        "src/index.ts",
        "src/components/index.ts",
        "src/auth/jwt.ts",
        "src/auth/login.tsx",
        "src/utils.ts",
        "package.json",
    }


def test_extract_path_mentions() -> None:
    """Test extracting path mentions with backticks, bare paths, and punctuation."""
    text = (
        "Check `src/auth/jwt.ts` and ./src/utils.ts for details. "
        "Also see login.tsx and package.json! (src/index.ts), not https://example.com/foo.ts."
    )
    mentions = extract_path_mentions(text)
    raw_texts = [m.raw for m in mentions]
    cleaned_texts = [m.cleaned for m in mentions]

    assert "`src/auth/jwt.ts`" in raw_texts
    assert "src/auth/jwt.ts" in cleaned_texts
    assert "./src/utils.ts" in cleaned_texts
    assert "login.tsx" in cleaned_texts
    assert "package.json" in cleaned_texts
    assert "src/index.ts" in cleaned_texts

    # URL should be excluded
    assert not any("example.com" in m.cleaned for m in mentions)


def test_verify_mentions_exact_and_suffix(sample_graph_nodes: set[str]) -> None:
    """Test exact match and unique suffix match verification."""
    text = "Look at `src/auth/jwt.ts` and login.tsx."
    mentions = extract_path_mentions(text)

    verified, flagged = verify_mentions(mentions, sample_graph_nodes)

    assert "`src/auth/jwt.ts`" in verified
    assert verified["`src/auth/jwt.ts`"] == "src/auth/jwt.ts"

    # login.tsx is unique suffix for src/auth/login.tsx
    assert "login.tsx" in verified
    assert verified["login.tsx"] == "src/auth/login.tsx"

    assert len(flagged) == 0


def test_verify_mentions_ambiguous(sample_graph_nodes: set[str]) -> None:
    """Test ambiguous suffix match is flagged (e.g., index.ts has two matches)."""
    text = "Refer to index.ts."
    mentions = extract_path_mentions(text)

    verified, flagged = verify_mentions(mentions, sample_graph_nodes)
    assert len(verified) == 0
    assert len(flagged) == 1
    assert flagged[0].cleaned == "index.ts"


def test_verify_mentions_invented(sample_graph_nodes: set[str]) -> None:
    """Test invented / non-existent path is flagged."""
    text = "Refer to `src/fake/invented.ts` and ghost.tsx."
    mentions = extract_path_mentions(text)

    verified, flagged = verify_mentions(mentions, sample_graph_nodes)
    assert len(verified) == 0
    assert len(flagged) == 2
    assert flagged[0].cleaned == "src/fake/invented.ts"
    assert flagged[1].cleaned == "ghost.tsx"


def test_annotate_flagged_mentions(sample_graph_nodes: set[str]) -> None:
    """Test annotate adds warning markers after flagged mentions."""
    text = "Check `src/auth/jwt.ts` and `src/fake.ts`."
    mentions = extract_path_mentions(text)

    verified, flagged = verify_mentions(mentions, sample_graph_nodes)
    annotated = annotate(text, flagged)

    # Verified path should NOT be annotated
    assert "`src/auth/jwt.ts` ⚠unverified" not in annotated
    # Flagged path MUST be annotated
    assert "`src/fake.ts` ⚠unverified" in annotated
