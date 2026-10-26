import json

import pytest

from app.parser.tsconfig import load_tsconfigs, parse_jsonc


def test_parse_jsonc_comments_and_trailing_commas() -> None:
    text = """
    {
        // Single line comment
        "compilerOptions": {
            /* Block comment */
            "target": "ESNext",
            "module": "NodeNext", // inline comment
            "paths": {
                "@/*": ["src/*"],
            },
        },
        "include": [
            "src/**/*",
            "tests/**/*",
        ],
    }
    """
    data = parse_jsonc(text)
    assert data["compilerOptions"]["target"] == "ESNext"
    assert data["compilerOptions"]["module"] == "NodeNext"
    assert data["compilerOptions"]["paths"]["@/*"] == ["src/*"]
    assert data["include"] == ["src/**/*", "tests/**/*"]


def test_parse_jsonc_strings_with_comments_and_escapes() -> None:
    text = r"""
    {
        "url": "https://example.com/api//v1",
        "block": "some /* not a comment */ here",
        "escaped": "quoted \"value\" // still inside string",
        "trailing": 42,
    }
    """
    data = parse_jsonc(text)
    assert data["url"] == "https://example.com/api//v1"
    assert data["block"] == "some /* not a comment */ here"
    assert data["escaped"] == 'quoted "value" // still inside string'
    assert data["trailing"] == 42


def test_parse_jsonc_invalid_raises() -> None:
    with pytest.raises(json.JSONDecodeError):
        parse_jsonc("{ invalid json without quotes: 123 }")


def test_load_tsconfigs_basic_and_for_file() -> None:
    files = {
        "tsconfig.json": b"""{
            "compilerOptions": {
                "baseUrl": ".",
                "paths": {
                    "@/*": ["src/*"],
                    "components/*": ["src/components/*"]
                }
            }
        }""",
        "src/index.ts": b"export const a = 1;",
    }
    index = load_tsconfigs(files)
    assert len(index.warnings) == 0

    cfg = index.for_file("src/index.ts")
    assert cfg is not None
    assert cfg.path == "tsconfig.json"
    assert cfg.base_url == ""
    assert cfg.paths["@/*"] == ["src/*"]
    assert cfg.paths["components/*"] == ["src/components/*"]


def test_load_tsconfigs_monorepo_nearest_selection() -> None:
    files = {
        "tsconfig.json": b"""{
            "compilerOptions": {
                "paths": {
                    "root/*": ["packages/*"]
                }
            }
        }""",
        "packages/pkg-a/tsconfig.json": b"""{
            "compilerOptions": {
                "baseUrl": "./src",
                "paths": {
                    "@pkg-a/*": ["*"]
                }
            }
        }""",
        "packages/pkg-b/tsconfig.json": b"""{
            "compilerOptions": {
                "paths": {
                    "@pkg-b/*": ["src/*"]
                }
            }
        }""",
        "packages/pkg-a/src/feature.ts": b"export const featA = 1;",
        "packages/pkg-b/src/feature.ts": b"export const featB = 2;",
        "root_file.ts": b"export const root = true;",
    }
    index = load_tsconfigs(files)

    cfg_a = index.for_file("packages/pkg-a/src/feature.ts")
    assert cfg_a is not None
    assert cfg_a.path == "packages/pkg-a/tsconfig.json"
    assert cfg_a.base_url == "packages/pkg-a/src"
    assert cfg_a.paths["@pkg-a/*"] == ["packages/pkg-a/src/*"]

    cfg_b = index.for_file("packages/pkg-b/src/feature.ts")
    assert cfg_b is not None
    assert cfg_b.path == "packages/pkg-b/tsconfig.json"
    assert cfg_b.paths["@pkg-b/*"] == ["packages/pkg-b/src/*"]

    cfg_root = index.for_file("root_file.ts")
    assert cfg_root is not None
    assert cfg_root.path == "tsconfig.json"


def test_load_tsconfigs_extends_resolution() -> None:
    files = {
        "tsconfig.base.json": b"""{
            "compilerOptions": {
                "baseUrl": ".",
                "paths": {
                    "@base/*": ["base/*"]
                }
            }
        }""",
        "packages/app/tsconfig.json": b"""{
            "extends": "../../tsconfig.base.json",
            "compilerOptions": {
                "paths": {
                    "@app/*": ["src/*"]
                }
            }
        }""",
    }
    index = load_tsconfigs(files)
    cfg = index.for_file("packages/app/src/index.ts")
    assert cfg is not None
    assert cfg.path == "packages/app/tsconfig.json"
    # Child paths override / merge compilerOptions
    assert "@app/*" in cfg.paths


def test_load_tsconfigs_extends_cycle_safe() -> None:
    files = {
        "tsconfig.a.json": b'{"extends": "./tsconfig.b.json"}',
        "tsconfig.b.json": b'{"extends": "./tsconfig.a.json"}',
    }
    # Must not raise or recurse infinitely
    index = load_tsconfigs(files)
    assert isinstance(index, object)


def test_load_tsconfigs_invalid_json_adds_warning() -> None:
    files = {
        "tsconfig.json": b"{ invalid json: 123",
    }
    index = load_tsconfigs(files)
    assert len(index.warnings) > 0
    assert index.for_file("src/index.ts") is None
