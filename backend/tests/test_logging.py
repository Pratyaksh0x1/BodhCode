import logging

from app.logging_setup import TokenRedactionFilter, redact_tokens


def test_redact_tokens_each_shape():
    tokens = [
        ("ghp_1234567890abcdefghijklmnopqrstuvwxyz", "[REDACTED]"),
        ("gho_oauthToken1234567890abcdef", "[REDACTED]"),
        ("ghu_userToServerToken1234567890", "[REDACTED]"),
        ("github_pat_11AABC_1234567890abcdefghijk", "[REDACTED]"),
        ("gsk_sampleGroqKey1234567890abcdefghij", "[REDACTED]"),
        ("lsv2_pt_sampleLangsmithKey1234567890", "[REDACTED]"),
        ("Bearer secret_jwt_token_payload", "Bearer [REDACTED]"),
    ]

    for raw_token, expected in tokens:
        input_text = f"Connecting with token: {raw_token} completed."
        redacted = redact_tokens(input_text)
        assert raw_token not in redacted
        assert expected in redacted


def test_token_redaction_filter_record():
    log_filter = TokenRedactionFilter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Error authenticating with gsk_99999999 and Bearer eyJhbGciOi",
        args=(),
        exc_info=None,
    )

    result = log_filter.filter(record)
    assert result is True
    assert "gsk_99999999" not in record.msg
    assert "Bearer eyJhbGciOi" not in record.msg
    assert "[REDACTED]" in record.msg
    assert "Bearer [REDACTED]" in record.msg
