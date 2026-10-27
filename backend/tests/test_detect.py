"""Tests for pure language detection module."""

from app.i18n.detect import detect_language


def test_detect_japanese():
    text = (
        "# プロジェクト概要\n\n"
        "このリポジトリは、TypeScriptおよびJavaScriptの依存関係を解析するためのツールです。"
        "グラフ理論とAST構文解析を用いて、影響範囲を正確に特定します。"
    )
    result = detect_language(text)
    assert result.code == "ja"
    assert result.confidence > 0.8


def test_detect_hindi():
    text = (
        "# परियोजना परिचय\n\n"
        "यह एक ओपन सोर्स सॉफ्टवेयर प्रोजेक्ट है जो कोड की निर्भरताओं को समझने में मदद करता है।"
        "उपयोगकर्ता आसानी से अपने पसंदीदा भाषा में संदर्भ देख सकते हैं।"
    )
    result = detect_language(text)
    assert result.code == "hi"
    assert result.confidence > 0.8


def test_detect_spanish():
    text = (
        "# Descripción del proyecto\n\n"
        "Esta biblioteca proporciona un conjunto de herramientas para analizar las dependencias "
        "en proyectos modernos de TypeScript y JavaScript."
    )
    result = detect_language(text)
    assert result.code == "es"
    assert result.confidence > 0.8


def test_detect_english():
    text = (
        "# BodhCode Project\n\n"
        "BodhCode turns public GitHub repositories into interactive dependency maps, "
        "translates context into your native language, and enables browser-based code navigation."
    )
    result = detect_language(text)
    assert result.code == "en"
    assert result.confidence > 0.8


def test_detect_too_short_text():
    result = detect_language("Hello world")
    assert result.code is None
    assert result.confidence == 0.0


def test_detect_code_heavy_sample():
    # Mostly code, but has enough prose to detect Japanese
    text = (
        "```typescript\n"
        "export function add(a: number, b: number): number {\n"
        "  return a + b;\n"
        "}\n"
        "```\n\n"
        "この関数は2つの数値を加算して結果を返します。テストを実行するにはコマンドを実行してください。"
    )
    result = detect_language(text)
    assert result.code == "ja"


def test_detect_code_only_sample():
    # Only code and stack trace, prose < 20 chars
    text = (
        "```typescript\n"
        "const a = 10;\n"
        "console.log(a);\n"
        "```\n"
        "at Object.<anonymous> (test.js:1:1)\n"
        "https://example.com/error"
    )
    result = detect_language(text)
    assert result.code is None
