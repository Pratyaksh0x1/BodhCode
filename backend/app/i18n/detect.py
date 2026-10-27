"""Pure language detection utility using lingua-language-detector."""

import re
from dataclasses import dataclass

from lingua import LanguageDetector, LanguageDetectorBuilder

from app.i18n.languages import is_supported

MAX_DETECTION_CHARS = 4000
MIN_TEXT_LENGTH = 20

# Build detector once at module load
_detector: LanguageDetector = LanguageDetectorBuilder.from_all_spoken_languages().build()

# Regex patterns for stripping non-prose elements before detection
_FENCED_CODE_RE = re.compile(r"```[\s\S]*?```|~~~[\s\S]*?~~~")
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_URL_RE = re.compile(r"https?://\S+|<https?://[^>]+>")
_STACK_TRACE_LINE_RE = re.compile(
    r"^\s*(?:at\s+|File\s+\".*\",\s+line\s+\d+|Traceback\s*\(|(?:\w+Error|\w+Exception):|#\d+\s+0x).*",
    re.MULTILINE,
)
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class Detection:
    """Language detection outcome with ISO 639-1 code and confidence score."""

    code: str | None
    confidence: float


def strip_code_and_noise(text: str) -> str:
    """Remove code blocks, inline code, URLs, and stack traces before language detection."""
    stripped = _FENCED_CODE_RE.sub(" ", text)
    stripped = _INLINE_CODE_RE.sub(" ", stripped)
    stripped = _URL_RE.sub(" ", stripped)
    stripped = _STACK_TRACE_LINE_RE.sub(" ", stripped)
    cleaned = _WHITESPACE_RE.sub(" ", stripped).strip()
    return cleaned


def detect_language(text: str) -> Detection:
    """Detect the natural language of markdown or plain text.

    Truncates input to MAX_DETECTION_CHARS, strips code, URLs, and stack traces.
    Returns code=None if remaining text is shorter than MIN_TEXT_LENGTH or if
    the detected language falls outside BodhCode's supported catalogue.
    """
    truncated = text[:MAX_DETECTION_CHARS]
    cleaned = strip_code_and_noise(truncated)

    if len(cleaned) < MIN_TEXT_LENGTH:
        return Detection(code=None, confidence=0.0)

    try:
        confidences = _detector.compute_language_confidence_values(cleaned)
    except Exception:
        return Detection(code=None, confidence=0.0)

    if not confidences:
        return Detection(code=None, confidence=0.0)

    top = confidences[0]
    if top.value <= 0.0 or not top.language.iso_code_639_1:
        return Detection(code=None, confidence=0.0)

    code = top.language.iso_code_639_1.name.lower()
    confidence = float(top.value)

    if not is_supported(code):
        return Detection(code=None, confidence=confidence)

    return Detection(code=code, confidence=confidence)
