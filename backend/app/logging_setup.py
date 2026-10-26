import logging
import re

# Pattern matching sensitive tokens:
# - ghp_: GitHub Personal Access Token (classic)
# - gho_: GitHub OAuth Access Token
# - ghu_: GitHub User-to-Server Token
# - github_pat_: GitHub Fine-Grained Personal Access Token
# - gsk_: Groq API Key
# - lsv2_: LangSmith API Key
# - Bearer <token>: Authorization Bearer tokens
TOKEN_PATTERN = re.compile(
    r"\b(ghp_[a-zA-Z0-9]+|"
    r"gho_[a-zA-Z0-9]+|"
    r"ghu_[a-zA-Z0-9]+|"
    r"github_pat_[a-zA-Z0-9_]+|"
    r"gsk_[a-zA-Z0-9]+|"
    r"lsv2_[a-zA-Z0-9_]+)\b|"
    r"(Bearer\s+[^\s,;]+)",
    re.IGNORECASE,
)


def redact_tokens(text: str) -> str:
    """Redact sensitive token patterns from text."""

    def _replace(match: re.Match[str]) -> str:
        bearer_group = match.group(2)
        if bearer_group:
            return "Bearer [REDACTED]"
        return "[REDACTED]"

    return TOKEN_PATTERN.sub(_replace, text)


class TokenRedactionFilter(logging.Filter):
    """Log filter that scrubs credentials and API tokens from log output."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_tokens(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: (redact_tokens(v) if isinstance(v, str) else v)
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    redact_tokens(v) if isinstance(v, str) else v for v in record.args
                )
        return True


def setup_logging(level: int = logging.INFO) -> None:
    """Configure standardized application logging with redaction filter."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Avoid adding duplicate handlers on re-configuration
    for handler in root_logger.handlers:
        handler.addFilter(TokenRedactionFilter())

    if not root_logger.handlers:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(formatter)
        console_handler.addFilter(TokenRedactionFilter())
        root_logger.addHandler(console_handler)
