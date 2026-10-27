from app.ai.redact import redact


def test_redact_token_shapes_in_strings():
    tokens = [
        "ghp_1234567890abcdefghij",
        "gho_ABCDEF1234567890xxxx",
        "ghu_99988877766655544433",
        "github_pat_11AAAAAAA_BBBBBBBBBBBBBBB",
        "gsk_abcdefghijklmnop1234567890",
        "lsv2_pt_11112222333344445555666677778888",
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz",
    ]
    for token in tokens:
        input_str = f"Connecting with token: {token} inside prompt"
        result = redact(input_str)
        assert token not in result
        assert "[REDACTED]" in result


def test_redact_sensitive_dict_keys():
    payload = {
        "user": "alice",
        "token": "sensitive_session_token_123",
        "GITHUB_TOKEN": "some_value",
        "user_api_key": "some_api_key",
        "secret": "fernet_secret",
        "password": "mypassword123",
        "cookie": "session_cookie=abc",
        "authorization": "Bearer custom_auth_token",
        "safe_field": "hello world",
    }
    redacted = redact(payload)
    assert redacted["user"] == "alice"
    assert redacted["safe_field"] == "hello world"
    assert redacted["token"] == "[REDACTED]"
    assert redacted["GITHUB_TOKEN"] == "[REDACTED]"
    assert redacted["user_api_key"] == "[REDACTED]"
    assert redacted["secret"] == "[REDACTED]"
    assert redacted["password"] == "[REDACTED]"
    assert redacted["cookie"] == "[REDACTED]"
    assert redacted["authorization"] == "[REDACTED]"


def test_redact_nested_structures():
    nested = {
        "level1": [
            {"api_key": "secret1"},
            {"message": "using gsk_999888777666555444332211 for calls"},
        ],
        "tuple_data": ("safe", "Bearer 1234567890abcdef"),
        "set_data": {"safe_element"},
        "primitives": 123,
    }
    redacted = redact(nested)
    assert redacted["level1"][0]["api_key"] == "[REDACTED]"
    assert "gsk_999888777666555444332211" not in redacted["level1"][1]["message"]
    assert "[REDACTED]" in redacted["level1"][1]["message"]
    assert redacted["tuple_data"] == ("safe", "[REDACTED]")
    assert redacted["primitives"] == 123
