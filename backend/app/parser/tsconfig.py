"""Pure parser and resolver for tsconfig.json and jsconfig.json configurations."""

import json
import posixpath
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TsConfig:
    """Parsed and normalized TypeScript / JavaScript configuration."""

    path: str
    dir_path: str
    base_url: str | None
    paths: dict[str, list[str]]
    raw: dict[str, Any] = field(default_factory=dict)


class TsConfigIndex:
    """Index mapping directory paths to their governing TsConfig."""

    def __init__(self, configs_by_dir: dict[str, TsConfig], warnings: list[str]) -> None:
        self._configs = configs_by_dir
        self.warnings = tuple(warnings)

    def for_file(self, file_path: str) -> TsConfig | None:
        """Find the nearest tsconfig in the file's directory chain."""
        dir_name = posixpath.dirname(file_path)
        while True:
            if dir_name in self._configs:
                return self._configs[dir_name]
            if not dir_name:
                break
            parent = posixpath.dirname(dir_name)
            if parent == dir_name:
                break
            dir_name = parent
        return self._configs.get("")


def parse_jsonc(text: str) -> dict[str, Any]:
    """Strip comments (// and /* */) and trailing commas from JSONC text, then parse."""
    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    escape = False

    while i < n:
        c = text[i]

        if in_string:
            out.append(c)
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_string = False
            i += 1
            continue

        # Outside string
        if c == '"':
            in_string = True
            escape = False
            out.append(c)
            i += 1
        elif c == "/" and i + 1 < n and text[i + 1] == "/":
            i += 2
            while i < n and text[i] != "\n":
                i += 1
        elif c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
        elif c == ",":
            # Check for trailing comma before } or ]
            j = i + 1
            while j < n:
                cj = text[j]
                if cj in (" ", "\t", "\r", "\n"):
                    j += 1
                elif cj == "/" and j + 1 < n and text[j + 1] == "/":
                    j += 2
                    while j < n and text[j] != "\n":
                        j += 1
                elif cj == "/" and j + 1 < n and text[j + 1] == "*":
                    j += 2
                    while j + 1 < n and not (text[j] == "*" and text[j + 1] == "/"):
                        j += 1
                    j += 2
                else:
                    break
            if j < n and text[j] in ("}", "]"):
                i += 1  # Skip trailing comma
            else:
                out.append(c)
                i += 1
        else:
            out.append(c)
            i += 1

    cleaned = "".join(out)
    return json.loads(cleaned)


def _normalize_repo_path(base_dir: str, rel_path: str) -> str:
    """Combine base directory and relative path into a normalized repo-relative POSIX path."""
    if base_dir:
        joined = posixpath.normpath(posixpath.join(base_dir, rel_path))
    else:
        joined = posixpath.normpath(rel_path)
    if joined in (".", "./"):
        return ""
    if joined.startswith("./"):
        joined = joined[2:]
    return joined


def _resolve_config(
    config_path: str,
    files: Mapping[str, bytes],
    visited: set[str],
    depth: int,
    warnings: list[str],
) -> TsConfig | None:
    """Load config and recursively resolve 'extends' up to depth 5."""
    if depth > 5 or config_path in visited:
        return None

    visited.add(config_path)
    raw_bytes = files.get(config_path)
    if not raw_bytes:
        return None

    try:
        text = raw_bytes.decode("utf-8", errors="replace")
        data = parse_jsonc(text)
    except Exception as err:
        warnings.append(f"Failed to parse {config_path}: {err}")
        return None

    if not isinstance(data, dict):
        return None

    dir_name = posixpath.dirname(config_path)
    raw_compiler = data.get("compilerOptions")
    compiler_opts = raw_compiler if isinstance(raw_compiler, dict) else {}

    raw_base_url = compiler_opts.get("baseUrl")
    norm_base_url: str | None = None
    if isinstance(raw_base_url, str):
        norm_base_url = _normalize_repo_path(dir_name, raw_base_url)

    path_base = norm_base_url if norm_base_url is not None else dir_name
    raw_paths = compiler_opts.get("paths", {})
    norm_paths: dict[str, list[str]] = {}
    if isinstance(raw_paths, dict):
        for pattern, targets in raw_paths.items():
            if isinstance(targets, list):
                norm_paths[pattern] = [
                    _normalize_repo_path(path_base, t) for t in targets if isinstance(t, str)
                ]
            elif isinstance(targets, str):
                norm_paths[pattern] = [_normalize_repo_path(path_base, targets)]

    extends_spec = data.get("extends")
    base_config: TsConfig | None = None

    is_rel = (
        isinstance(extends_spec, str)
        and (extends_spec.startswith("./") or extends_spec.startswith("../"))
    )
    if is_rel:
        base_path = _normalize_repo_path(dir_name, extends_spec)
        if not base_path.endswith(".json"):
            if f"{base_path}.json" in files:
                base_path = f"{base_path}.json"
            elif posixpath.join(base_path, "tsconfig.json") in files:
                base_path = posixpath.join(base_path, "tsconfig.json")

        if base_path in files:
            base_config = _resolve_config(
                base_path, files, visited.copy(), depth + 1, warnings
            )

    merged_paths = dict(base_config.paths) if base_config else {}
    merged_paths.update(norm_paths)

    effective_base_url = (
        norm_base_url
        if norm_base_url is not None
        else (base_config.base_url if base_config else None)
    )

    merged_raw = dict(base_config.raw) if base_config else {}
    merged_compiler = dict(merged_raw.get("compilerOptions", {}))
    merged_compiler.update(compiler_opts)
    merged_raw.update(data)
    merged_raw["compilerOptions"] = merged_compiler

    return TsConfig(
        path=config_path,
        dir_path=dir_name,
        base_url=effective_base_url,
        paths=merged_paths,
        raw=merged_raw,
    )


def load_tsconfigs(files: Mapping[str, bytes]) -> TsConfigIndex:
    """Find, parse, and index all tsconfig / jsconfig files in the repository."""
    warnings: list[str] = []
    candidates: dict[str, list[str]] = {}

    for path in files:
        filename = posixpath.basename(path).lower()
        is_tsconfig = filename.startswith("tsconfig") and filename.endswith(".json")
        if is_tsconfig or filename == "jsconfig.json":
            dir_name = posixpath.dirname(path)
            candidates.setdefault(dir_name, []).append(path)

    configs_by_dir: dict[str, TsConfig] = {}

    for dir_name, path_list in candidates.items():
        # Prefer exact tsconfig.json over others
        selected_path = next(
            (p for p in path_list if posixpath.basename(p) == "tsconfig.json"),
            None,
        )
        if not selected_path:
            selected_path = next(
                (p for p in path_list if posixpath.basename(p) == "jsconfig.json"),
                path_list[0],
            )

        cfg = _resolve_config(selected_path, files, set(), 0, warnings)
        if cfg:
            configs_by_dir[dir_name] = cfg

    return TsConfigIndex(configs_by_dir, warnings)
