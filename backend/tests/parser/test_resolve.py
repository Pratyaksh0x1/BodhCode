"""Unit tests for the pure module resolver."""

from app.parser.resolve import resolve
from app.parser.tsconfig import TsConfig
from app.parser.types import Resolution


def test_resolve_builtins() -> None:
    all_files: frozenset[str] = frozenset()
    # node: prefix
    res1 = resolve("src/index.ts", "node:fs/promises", all_files, None)
    assert res1 == Resolution(kind="builtin")

    # Name in NODE_BUILTINS constant
    res2 = resolve("src/index.ts", "path", all_files, None)
    assert res2 == Resolution(kind="builtin")

    res3 = resolve("src/index.ts", "fs", all_files, None)
    assert res3 == Resolution(kind="builtin")


def test_resolve_relative_and_esm_mapping() -> None:
    all_files = frozenset({"src/util.ts", "src/comp.tsx", "src/helper.mts"})

    # Exact match when util.ts is requested
    res1 = resolve("src/main.ts", "./util.ts", all_files, None)
    assert res1 == Resolution(kind="file", target="src/util.ts")

    # ESM .js -> .ts mapping
    res2 = resolve("src/main.ts", "./util.js", all_files, None)
    assert res2 == Resolution(kind="file", target="src/util.ts")

    # ESM .jsx -> .tsx mapping
    res3 = resolve("src/main.ts", "./comp.jsx", all_files, None)
    assert res3 == Resolution(kind="file", target="src/comp.tsx")

    # ESM .mjs -> .mts mapping
    res4 = resolve("src/main.ts", "./helper.mjs", all_files, None)
    assert res4 == Resolution(kind="file", target="src/helper.mts")

    # Missing relative file -> unresolved (never external)
    res5 = resolve("src/main.ts", "./missing.js", all_files, None)
    assert res5 == Resolution(kind="unresolved", reason="file_not_found")

    # Escaping repo root -> unresolved
    res6 = resolve("src/main.ts", "../../outside.ts", all_files, None)
    assert res6 == Resolution(kind="unresolved", reason="outside_repo")


def test_resolve_directory_index() -> None:
    all_files = frozenset({"src/components/index.tsx", "src/api/index.ts"})

    res1 = resolve("src/index.ts", "./components", all_files, None)
    assert res1 == Resolution(kind="file", target="src/components/index.tsx")

    res2 = resolve("src/index.ts", "./api", all_files, None)
    assert res2 == Resolution(kind="file", target="src/api/index.ts")


def test_resolve_tsconfig_paths_aliases() -> None:
    tsconfig = TsConfig(
        path="tsconfig.json",
        dir_path="",
        base_url="",
        paths={
            "@/*": ["src/*"],
            "@components/*": ["src/components/*"],
        },
    )
    all_files = frozenset({"src/components/Button.tsx", "src/utils/math.ts"})

    # @/* alias
    res1 = resolve("src/pages/Home.tsx", "@/utils/math", all_files, tsconfig)
    assert res1 == Resolution(kind="file", target="src/utils/math.ts")

    # @components/* alias (more specific)
    res2 = resolve("src/pages/Home.tsx", "@components/Button", all_files, tsconfig)
    assert res2 == Resolution(kind="file", target="src/components/Button.tsx")

    # Removed alias falls through to external with normalized package
    res3 = resolve("src/pages/Home.tsx", "@/components/Button", all_files, None)
    assert res3 == Resolution(kind="external", package="@/components")


def test_resolve_externals() -> None:
    all_files: frozenset[str] = frozenset({"src/index.ts"})

    res1 = resolve("src/index.ts", "react", all_files, None)
    assert res1 == Resolution(kind="external", package="react")

    res2 = resolve("src/index.ts", "lodash/fp", all_files, None)
    assert res2 == Resolution(kind="external", package="lodash")

    res3 = resolve("src/index.ts", "@scope/pkg/deep/path", all_files, None)
    assert res3 == Resolution(kind="external", package="@scope/pkg")

    res4 = resolve("src/index.ts", "@tanstack/react-query", all_files, None)
    assert res4 == Resolution(kind="external", package="@tanstack/react-query")
