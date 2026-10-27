"""Tests for pure markdown masking and unmasking module."""

from app.i18n.mask import mask_protected, placeholders_intact, unmask


def test_mask_round_trip():
    sample = (
        "# Sample Document\n\n"
        "Here is some text with @developer and issue #42.\n"
        "Commit sha is 7f3b89a0c1d2e3f4a5b6c7d8e9f0123456789abc.\n"
        "Short sha is e1a2b3c.\n\n"
        "Check this link: [BodhCode Documentation](https://bodhcode.dev/docs) or raw "
        "https://github.com/bodhcode/bodhcode.\n\n"
        "Inline code: `const x = 42;` and file `src/parser/extract.py`.\n\n"
        "```typescript\n"
        "function hello(name: string): string {\n"
        "  return `Hello, ${name}!`;\n"
        "}\n"
        "```\n\n"
        "Error trace:\n"
        "at Object.<anonymous> (/app/src/index.js:14:11)\n\n"
        "<div class=\"warning\">Please read carefully</div>\n"
    )

    masked, mapping = mask_protected(sample)

    # Protected items should not appear as plain text in masked string
    assert "```typescript" not in masked
    assert "const x = 42;" not in masked
    assert "https://bodhcode.dev/docs" not in masked
    assert "https://github.com/bodhcode/bodhcode" not in masked
    assert "@developer" not in masked
    assert "#42" not in masked
    assert "7f3b89a0c1d2e3f4a5b6c7d8e9f0123456789abc" not in masked
    assert "at Object.<anonymous>" not in masked
    assert "<div class=\"warning\">" not in masked

    # But prose and link text SHOULD remain unmasked
    assert "Sample Document" in masked
    assert "Here is some text with" in masked
    assert "[BodhCode Documentation](" in masked
    assert "Please read carefully" in masked

    # Placeholders should be intact
    assert placeholders_intact(masked, mapping)

    # Unmask should restore original sample byte-for-byte
    restored = unmask(masked, mapping)
    assert restored == sample


def test_placeholders_intact_validation():
    mapping = {"⟦K0⟧": "code", "⟦K1⟧": "url", "⟦K2⟧": "#12"}

    # Exact match
    text = "Translate this: ⟦K0⟧ and ⟦K1⟧ then ⟦K2⟧."
    assert placeholders_intact(text, mapping) is True

    # Missing a placeholder
    text_missing = "Translate this: ⟦K0⟧ and then ⟦K2⟧."
    assert placeholders_intact(text_missing, mapping) is False

    # Duplicated placeholder
    text_dup = "Translate this: ⟦K0⟧ and ⟦K1⟧ then ⟦K2⟧ and ⟦K0⟧."
    assert placeholders_intact(text_dup, mapping) is False

    # Unknown placeholder
    text_unknown = "Translate this: ⟦K0⟧ and ⟦K1⟧ then ⟦K2⟧ and ⟦K99⟧."
    assert placeholders_intact(text_unknown, mapping) is False
