"""Pure markdown masking and unmasking for translation protection."""

import re

# Unique Unicode bracket markers that rarely appear in natural prose or code
_PLACEHOLDER_RE = re.compile(r"⟦K\d+⟧")

_FENCED_CODE_RE = re.compile(r"```[\s\S]*?```|~~~[\s\S]*?~~~")
_STACK_TRACE_RE = re.compile(
    r"(?:^\s*Traceback \(most recent call last\):(?:\n\s+File.*|\n\s+.*)+)"
    r"|(?:^\s*at\s+[\w\.\$<>\[\]\s/\\:-]+(?:\([^\)]*\)|:\d+:\d+)?\s*$)"
    r"|(?:^\s*File\s+\"[^\"]+\",\s+line\s+\d+.*$)"
    r"|(?:^\s*(?:[A-Za-z0-9_]+Error|[A-Za-z0-9_]+Exception):\s+.*$)",
    re.MULTILINE,
)
_HTML_TAG_RE = re.compile(r"<!--[\s\S]*?-->|<[a-zA-Z\/][^>]*?>")
_MD_LINK_TARGET_RE = re.compile(r"(\[[^\]]*\]\()([^\s\)\"]+)(\s*(?:\"[^\"]*\")?\))")
_AUTOLINK_RE = re.compile(r"<https?://[^>]+>")
_RAW_URL_RE = re.compile(r"https?://[a-zA-Z0-9\-._~:/?#\[\]@!$&'*+,;=%]+")
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_FULL_SHA_RE = re.compile(r"\b[0-9a-fA-F]{40}\b")
_SHORT_SHA_RE = re.compile(r"\b(?=[0-9a-fA-F]*[0-9])(?=[0-9a-fA-F]*[a-fA-F])[0-9a-fA-F]{7,12}\b")
_ISSUE_REF_RE = re.compile(r"(^|[\s\(\[])(#\d+)\b")
_MENTION_RE = re.compile(r"(^|[\s\(\[])(@[a-zA-Z0-9](?:[a-zA-Z0-9]|-(?=[a-zA-Z0-9])){0,38})\b")


def mask_protected(text: str) -> tuple[str, dict[str, str]]:
    """Replace protected code, links, stack traces, and identifiers with unique placeholders.

    Returns the masked text and a mapping from placeholder string to original substring.
    """
    mapping: dict[str, str] = {}
    counter = 0

    def replace_match(match: re.Match[str]) -> str:
        nonlocal counter
        token = f"⟦K{counter}⟧"
        counter += 1
        mapping[token] = match.group(0)
        return token

    # 1. Fenced code blocks
    text = _FENCED_CODE_RE.sub(replace_match, text)

    # 2. Stack traces
    text = _STACK_TRACE_RE.sub(replace_match, text)

    # 3. HTML tags & comments
    text = _HTML_TAG_RE.sub(replace_match, text)

    # 4. Markdown link targets: preserve the link text, mask only the URL target
    def replace_link_target(match: re.Match[str]) -> str:
        nonlocal counter
        prefix = match.group(1)
        url = match.group(2)
        suffix = match.group(3)
        token = f"⟦K{counter}⟧"
        counter += 1
        mapping[token] = url
        return f"{prefix}{token}{suffix}"

    text = _MD_LINK_TARGET_RE.sub(replace_link_target, text)

    # 5. Autolinks and raw URLs
    text = _AUTOLINK_RE.sub(replace_match, text)
    text = _RAW_URL_RE.sub(replace_match, text)

    # 6. Inline code (includes file paths in backticks)
    text = _INLINE_CODE_RE.sub(replace_match, text)

    # 7. Commit SHAs
    text = _FULL_SHA_RE.sub(replace_match, text)
    text = _SHORT_SHA_RE.sub(replace_match, text)

    # 8. Issue references (#123)
    def replace_issue(match: re.Match[str]) -> str:
        nonlocal counter
        prefix = match.group(1)
        issue = match.group(2)
        token = f"⟦K{counter}⟧"
        counter += 1
        mapping[token] = issue
        return f"{prefix}{token}"

    text = _ISSUE_REF_RE.sub(replace_issue, text)

    # 9. Mentions (@user)
    def replace_mention(match: re.Match[str]) -> str:
        nonlocal counter
        prefix = match.group(1)
        mention = match.group(2)
        token = f"⟦K{counter}⟧"
        counter += 1
        mapping[token] = mention
        return f"{prefix}{token}"

    text = _MENTION_RE.sub(replace_mention, text)

    return text, mapping


def unmask(text: str, mapping: dict[str, str]) -> str:
    """Restore all placeholders to their original substrings in a single pass."""
    if not mapping:
        return text

    def repl(match: re.Match[str]) -> str:
        token = match.group(0)
        return mapping.get(token, token)

    return _PLACEHOLDER_RE.sub(repl, text)


def placeholders_intact(translated: str, mapping: dict[str, str]) -> bool:
    """Verify that every placeholder in the mapping appears exactly once in translated text."""
    if not mapping:
        return True

    found_placeholders = _PLACEHOLDER_RE.findall(translated)
    if len(found_placeholders) != len(mapping):
        return False

    for token in mapping:
        if translated.count(token) != 1:
            return False

    for token in found_placeholders:
        if token not in mapping:
            return False

    return True
