"""Pure path extraction and graph verification utilities.

Extracts path-like mentions from model-generated text and cross-references them against
the verified dependency graph. Unverified or ambiguous mentions are flagged and annotated.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

import networkx as nx

# File extensions commonly used in TS/JS and modern repositories
_COMMON_EXTENSIONS = (
    "ts",
    "tsx",
    "js",
    "jsx",
    "mjs",
    "cjs",
    "json",
    "css",
    "scss",
    "html",
    "md",
    "yaml",
    "yml",
    "svg",
    "py",
    "rs",
    "go",
)

_EXT_PATTERN = "|".join(_COMMON_EXTENSIONS)

_URL_RE = re.compile(r"https?://[^\s)\]}>\"']+", re.IGNORECASE)

_MENTION_RE = re.compile(
    rf"(?P<backtick>`(?P<bt_content>[^`\n]+)`)|"
    rf"(?P<bare>(?:\.{{1,2}}/[a-zA-Z0-9_\-./]+|[a-zA-Z0-9_\-]+/[a-zA-Z0-9_\-./]+))|"
    rf"(?P<ext_file>\b[a-zA-Z0-9_\-]+\.(?:{_EXT_PATTERN})\b)",
    re.IGNORECASE,
)

_LEADING_PUNCT = "([{\"<' \t\n"
_TRAILING_PUNCT = ")]}\"'>,.:;?! \t\n"


@dataclass(frozen=True)
class Mention:
    """A path-like token identified in text."""

    raw: str
    cleaned: str
    start: int
    end: int


def _is_url(text: str) -> bool:
    """Check if token is an HTTP/HTTPS URL."""
    lower = text.lower()
    return lower.startswith("http://") or lower.startswith("https://")


def extract_path_mentions(text: str) -> list[Mention]:
    """Find all path-like tokens in text with character offsets.

    Handles backtick code spans, bare paths, relative paths, and extensions.
    Punctuation at boundaries is stripped while maintaining exact character offsets.
    """
    mentions: list[Mention] = []
    seen_spans: set[tuple[int, int]] = set()

    # Pre-calculate URL spans to avoid matching paths inside URLs
    url_spans = [(m.start(), m.end()) for m in _URL_RE.finditer(text)]

    for match in _MENTION_RE.finditer(text):
        m_start = match.start()
        m_end = match.end()

        # Skip if within a URL
        if any(us <= m_start and m_end <= ue for us, ue in url_spans):
            continue

        if match.group("backtick"):
            # Token inside backticks
            content = match.group("bt_content").strip()
            if _is_url(content):
                continue
            quoted_paths = re.findall(r'["\']([^"\'\n\r]+)["\']', content)
            candidates = quoted_paths if quoted_paths else [content]
            for cand in candidates:
                cand_clean = cand.strip()
                if " " in cand_clean or not cand_clean or _is_url(cand_clean):
                    continue
                has_slash = "/" in cand_clean or "\\" in cand_clean
                has_ext = any(cand_clean.lower().endswith(f".{ext}") for ext in _COMMON_EXTENSIONS)
                if has_slash or has_ext:
                    raw_match = match.group("backtick") if len(candidates) == 1 else cand_clean
                    mentions.append(
                        Mention(
                            raw=raw_match,
                            cleaned=cand_clean,
                            start=m_start,
                            end=m_end,
                        )
                    )
            seen_spans.add((m_start, m_end))
        else:
            # Check if this token was already enclosed by a backtick match
            if any(s <= m_start and m_end <= e for s, e in seen_spans):
                continue

            raw_token = match.group(0)
            if _is_url(raw_token):
                continue

            # Strip boundary punctuation and recalculate offsets
            l_strip = 0
            while l_strip < len(raw_token) and raw_token[l_strip] in _LEADING_PUNCT:
                l_strip += 1

            r_strip = len(raw_token)
            while r_strip > l_strip and raw_token[r_strip - 1] in _TRAILING_PUNCT:
                r_strip -= 1

            cleaned = raw_token[l_strip:r_strip].strip()
            if not cleaned or _is_url(cleaned):
                continue

            # Ensure valid filename or path structure
            has_slash = "/" in cleaned or "\\" in cleaned
            has_ext = any(cleaned.lower().endswith(f".{ext}") for ext in _COMMON_EXTENSIONS)
            if not (has_slash or has_ext):
                continue

            final_start = m_start + l_strip
            final_end = m_start + r_strip
            actual_raw = text[final_start:final_end]

            mentions.append(
                Mention(
                    raw=actual_raw,
                    cleaned=cleaned,
                    start=final_start,
                    end=final_end,
                )
            )

    return mentions


def verify_mentions(
    mentions: list[Mention],
    graph: nx.DiGraph | Iterable[str],
) -> tuple[dict[str, str], list[Mention]]:
    """Cross-verify path mentions against graph node IDs.

    A mention verifies only if:
    1. It exactly matches a node ID, OR
    2. It is a unique suffix match (e.g., 'auth.ts' matches exactly one 'src/auth.ts').

    Ambiguous suffix matches (>1 match) or unknown paths (0 matches) are flagged.
    Returns:
        (verified: dict[mention_raw -> canonical_node_id], flagged: list[Mention])
    """
    if isinstance(graph, nx.DiGraph):
        node_ids = set(graph.nodes)
    else:
        node_ids = set(graph)

    verified: dict[str, str] = {}
    flagged: list[Mention] = []

    for mention in mentions:
        cand = mention.cleaned.replace("\\", "/").strip()
        if cand.startswith("./"):
            cand = cand[2:]

        # 1. Exact match
        if cand in node_ids:
            verified[mention.raw] = cand
            continue

        # 2. Suffix match
        # Must match either exact or "/suffix"
        suffix_matches = [node for node in node_ids if node == cand or node.endswith("/" + cand)]

        # 3. ESM .js -> .ts / .tsx resolution
        if not suffix_matches and cand.endswith(".js"):
            stem = cand[:-3]
            for ext in (".ts", ".tsx"):
                cand_esm = stem + ext
                suffix_matches.extend(
                    node for node in node_ids if node == cand_esm or node.endswith("/" + cand_esm)
                )

        if len(suffix_matches) == 1:
            verified[mention.raw] = suffix_matches[0]
        else:
            # Ambiguous (len > 1) or Unknown (len == 0)
            flagged.append(mention)

    return verified, flagged


def annotate(
    text: str,
    flagged: list[Mention],
    marker: str = " ⚠unverified",
) -> str:
    """Append a visible unverified warning marker after each flagged mention in text.

    Replaces from right-to-left so character offsets remain valid throughout splicing.
    """
    if not flagged:
        return text

    # Sort in descending order of end offset
    sorted_flagged = sorted(flagged, key=lambda m: m.end, reverse=True)
    result = text
    for m in sorted_flagged:
        result = result[: m.end] + marker + result[m.end :]

    return result
