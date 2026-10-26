"""Pure module resolver for TypeScript and JavaScript imports."""

import posixpath

from app.parser.tsconfig import TsConfig
from app.parser.types import Resolution

# Constant list of Node.js built-in module names
NODE_BUILTINS: frozenset[str] = frozenset(
    {
        "assert",
        "assert/strict",
        "async_hooks",
        "buffer",
        "child_process",
        "cluster",
        "console",
        "constants",
        "crypto",
        "dgram",
        "diagnostics_channel",
        "dns",
        "dns/promises",
        "domain",
        "events",
        "fs",
        "fs/promises",
        "http",
        "http2",
        "https",
        "inspector",
        "inspector/promises",
        "module",
        "net",
        "os",
        "path",
        "path/posix",
        "path/win32",
        "perf_hooks",
        "process",
        "punycode",
        "querystring",
        "readline",
        "readline/promises",
        "repl",
        "stream",
        "stream/consumers",
        "stream/promises",
        "stream/web",
        "string_decoder",
        "sys",
        "timers",
        "timers/promises",
        "tls",
        "trace_events",
        "tty",
        "url",
        "util",
        "util/types",
        "v8",
        "vm",
        "wasi",
        "worker_threads",
        "zlib",
    }
)

CANDIDATE_EXTENSIONS: tuple[str, ...] = (
    ".ts",
    ".tsx",
    ".d.ts",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".json",
)


def _try_candidate(candidate: str, all_files: frozenset[str]) -> str | None:
    """Check candidate path against all_files via exact match, ESM mappings, ext, or index."""
    norm = posixpath.normpath(candidate)
    if norm.startswith("./"):
        norm = norm[2:]
    elif norm == ".":
        norm = ""

    # Must not escape repository root
    if norm.startswith("../") or norm == "..":
        return None

    # a. exact path if it exists
    if norm and norm in all_files:
        return norm

    # b. ESM extension mapping
    if norm.endswith(".js"):
        base = norm[:-3]
        for esm_ext in (".ts", ".tsx"):
            target = f"{base}{esm_ext}"
            if target in all_files:
                return target
    elif norm.endswith(".jsx"):
        target = f"{norm[:-4]}.tsx"
        if target in all_files:
            return target
    elif norm.endswith(".mjs"):
        target = f"{norm[:-4]}.mts"
        if target in all_files:
            return target
    elif norm.endswith(".cjs"):
        target = f"{norm[:-4]}.cts"
        if target in all_files:
            return target

    # c. append each extension
    for ext in CANDIDATE_EXTENSIONS:
        target = f"{norm}{ext}"
        if target in all_files:
            return target

    # d. directory index: <dir>/index + each extension
    index_base = posixpath.join(norm, "index") if norm else "index"
    for ext in CANDIDATE_EXTENSIONS:
        target = f"{index_base}{ext}"
        if target in all_files:
            return target

    return None


def _match_path_pattern(spec: str, pattern: str) -> str | None:
    """Return matched wildcard string if spec matches pattern, or empty string for exact match."""
    if "*" not in pattern:
        return "" if spec == pattern else None
    prefix, suffix = pattern.split("*", 1)
    if (
        spec.startswith(prefix)
        and spec.endswith(suffix)
        and len(spec) >= len(prefix) + len(suffix)
    ):
        if suffix:
            return spec[len(prefix) : -len(suffix)]
        return spec[len(prefix) :]
    return None


def _pattern_specificity(pattern: str) -> tuple[int, int]:
    """Sort key for path patterns: longest prefix, then longest suffix."""
    if "*" in pattern:
        prefix, suffix = pattern.split("*", 1)
        return (len(prefix), len(suffix))
    return (len(pattern), 0)


def _normalize_package_name(spec: str) -> str:
    """Normalize package name from bare specifier.

    E.g. @scope/pkg/sub -> @scope/pkg, lodash/fp -> lodash.
    """
    if spec.startswith("@"):
        parts = spec.split("/")
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
        return spec
    return spec.split("/")[0]


def resolve(
    from_path: str,
    spec: str,
    all_files: frozenset[str],
    tsconfig: TsConfig | None,
) -> Resolution:
    """Resolve an import specifier to a repository file, external package, or builtin."""
    # 1. Node builtin module (node: prefix or in NODE_BUILTINS list)
    if spec.startswith("node:"):
        return Resolution(kind="builtin")
    if spec in NODE_BUILTINS:
        return Resolution(kind="builtin")

    # 2. Relative imports (./, ../, ., ..)
    if spec.startswith("./") or spec.startswith("../") or spec in (".", ".."):
        dir_name = posixpath.dirname(from_path)
        joined = (
            posixpath.normpath(posixpath.join(dir_name, spec))
            if dir_name
            else posixpath.normpath(spec)
        )
        if joined in (".", "./"):
            joined = ""

        # Leaving repo root yields unresolved
        if joined.startswith("../") or joined == "..":
            return Resolution(kind="unresolved")

        matched = _try_candidate(joined, all_files)
        if matched is not None:
            return Resolution(kind="file", target=matched)
        return Resolution(kind="unresolved")

    # 3. Path alias matching from tsconfig.paths
    if tsconfig and tsconfig.paths:
        matching_patterns: list[str] = []
        for pattern in tsconfig.paths:
            if _match_path_pattern(spec, pattern) is not None:
                matching_patterns.append(pattern)

        # Longest / most specific prefix wins
        matching_patterns.sort(key=_pattern_specificity, reverse=True)

        for pattern in matching_patterns:
            wildcard = _match_path_pattern(spec, pattern)
            targets = tsconfig.paths[pattern]
            for target_pattern in targets:
                sub_target = (
                    target_pattern.replace("*", wildcard)
                    if wildcard is not None
                    else target_pattern
                )
                matched = _try_candidate(sub_target, all_files)
                if matched is not None:
                    return Resolution(kind="file", target=matched)

    # 3b. baseUrl-relative bare specifiers
    if tsconfig and tsconfig.base_url is not None:
        candidate = (
            posixpath.normpath(posixpath.join(tsconfig.base_url, spec))
            if tsconfig.base_url
            else posixpath.normpath(spec)
        )
        matched = _try_candidate(candidate, all_files)
        if matched is not None:
            return Resolution(kind="file", target=matched)

    # Root-relative path (/path/to/file)
    if spec.startswith("/"):
        candidate = spec.lstrip("/")
        matched = _try_candidate(candidate, all_files)
        if matched is not None:
            return Resolution(kind="file", target=matched)
        return Resolution(kind="unresolved")

    # 4. Anything else bare -> external with normalized package
    pkg = _normalize_package_name(spec)
    return Resolution(kind="external", package=pkg)
