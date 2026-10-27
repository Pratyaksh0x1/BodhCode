"""Read-only tools for repository graph, code search, parsing, and translation."""

from __future__ import annotations

import re
from typing import Any

from app.ai.graph_tools import (
    blast_radius as graph_blast_radius,
)
from app.ai.graph_tools import (
    find_files as graph_find_files,
)
from app.ai.graph_tools import (
    get_file_exports as graph_get_file_exports,
)
from app.ai.graph_tools import (
    get_graph_summary as graph_get_graph_summary,
)
from app.ai.graph_tools import (
    list_dependencies as graph_list_dependencies,
)
from app.ai.graph_tools import (
    list_dependents as graph_list_dependents,
)
from app.ai.graph_tools import (
    read_file as graph_read_file,
)
from app.ai.tools.base import Tool, ToolContext, ToolResult
from app.ai.untrusted import wrap_untrusted
from app.files.service import normalize_path
from app.i18n.translate import translate_text as i18n_translate_text
from app.parser.extract import extract_file
from app.parser.resolve import resolve
from app.parser.tsconfig import load_tsconfigs


class ParseFileTool(Tool):
    """Parse a source file and extract AST facts and resolved imports deterministically."""

    name = "parse_file"
    description = (
        "Parse a TypeScript or JavaScript file using Tree-sitter on the effective working copy "
        "content. Returns imports with resolved file targets, exports, and flags. "
        "Deterministic — zero LLM."
    )
    permission = "read"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Normalized repository file path (e.g. 'src/auth/jwt.ts').",
            },
        },
        "required": ["path"],
    }

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        raw_path = args.get("path", "")
        try:
            path = normalize_path(raw_path)
        except Exception as exc:
            return ToolResult(
                ok=False,
                data={"error": f"Invalid path '{raw_path}': {exc}"},
                error=f"Invalid path '{raw_path}': {exc}",
                summary=f"parse_file {raw_path} (invalid path)",
            )

        content: str | None = None
        if ctx.files is not None:
            try:
                eff = ctx.files.read_effective(path)
                content = eff["content"]
            except Exception as exc:
                return ToolResult(
                    ok=False,
                    data={"error": f"Failed to read '{path}': {exc}"},
                    error=f"Failed to read '{path}': {exc}",
                    summary=f"parse_file {path} (not found)",
                )
        elif ctx.source_dir is not None:
            target = (ctx.source_dir / path).resolve()
            try:
                target.relative_to(ctx.source_dir.resolve())
            except ValueError:
                return ToolResult(
                    ok=False,
                    data={"error": "Path traversal detected"},
                    error="Path traversal detected",
                    summary=f"parse_file {path} (traversal)",
                )
            if not target.is_file():
                return ToolResult(
                    ok=False,
                    data={"error": f"File '{path}' does not exist on disk."},
                    error=f"File '{path}' does not exist on disk.",
                    summary=f"parse_file {path} (not found)",
                )
            content = target.read_text(encoding="utf-8", errors="replace")
        else:
            return ToolResult(
                ok=False,
                data={"error": "No file service or source directory configured."},
                error="No file service or source directory configured.",
                summary=f"parse_file {path} (error)",
            )

        source_bytes = content.encode("utf-8")
        facts = extract_file(path, source_bytes)

        if "skipped_unsupported" in facts.flags:
            return ToolResult(
                ok=True,
                data={
                    "path": path,
                    "skipped": True,
                    "flags": list(facts.flags),
                },
                summary=f"parse_file {path} (unsupported format)",
            )

        # Collect all active files in repo for import resolution
        all_files: set[str] = set()
        if ctx.files is not None:
            try:
                tree = ctx.files.list_files_tree()
                all_files = {item["path"] for item in tree if item.get("status") != "deleted"}
            except Exception:
                pass
        if not all_files and ctx.graph is not None:
            all_files = set(ctx.graph.nodes)

        # Check for tsconfig files
        tsconfig_index = None
        tsconfig_map: dict[str, bytes] = {}
        for f in all_files:
            lower = f.lower()
            if (
                lower.startswith("tsconfig")
                or lower.endswith("/tsconfig.json")
                or lower.startswith("jsconfig")
                or lower.endswith("/jsconfig.json")
            ):
                try:
                    if ctx.files is not None:
                        t_eff = ctx.files.read_effective(f)
                        tsconfig_map[f] = t_eff["content"].encode("utf-8")
                    elif ctx.source_dir is not None:
                        t_path = ctx.source_dir / f
                        if t_path.is_file():
                            tsconfig_map[f] = t_path.read_bytes()
                except Exception:
                    pass
        if tsconfig_map:
            try:
                tsconfig_index = load_tsconfigs(tsconfig_map)
            except Exception:
                tsconfig_index = None

        cfg = tsconfig_index.for_file(path) if tsconfig_index else None
        frozen_all = frozenset(all_files)

        resolved_imports = []
        for imp in facts.imports:
            res = resolve(path, imp.specifier, frozen_all, cfg)
            resolved_imports.append(
                {
                    "specifier": imp.specifier,
                    "kind": imp.kind,
                    "line": imp.line,
                    "type_only": imp.type_only,
                    "target": res.target,
                    "resolution_kind": res.kind,
                }
            )

        data = {
            "path": path,
            "imports": resolved_imports,
            "exports": list(facts.exports),
            "has_default_export": facts.has_default_export,
            "unresolved_dynamic": facts.unresolved_dynamic,
            "flags": list(facts.flags),
        }
        return ToolResult(
            ok=True,
            data=data,
            summary=(
                f"parse_file {path} ({len(resolved_imports)} imports, {len(facts.exports)} exports)"
            ),
        )


class GetGraphSummaryTool(Tool):
    """Retrieve high-level dependency graph metrics and top fan-in modules."""

    name = "get_graph_summary"
    description = (
        "Get high-level repository graph statistics including file count, edge count, "
        "strongly connected cycles, and top files with the most dependents."
    )
    permission = "read"
    parameters = {
        "type": "object",
        "properties": {},
    }

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        data = graph_get_graph_summary(ctx.graph)
        if ctx.files is not None:
            try:
                changes = ctx.files.get_changes()
                if changes:
                    data["working_copy_changes_count"] = len(changes)
                    data["note"] = (
                        "Graph reflects original commit; working copy has uncommitted changes."
                    )
            except Exception:
                pass
        return ToolResult(
            ok=True,
            data=data,
            summary=f"get_graph_summary ({data.get('total_files', 0)} files)",
        )


class ListDependenciesTool(Tool):
    """List direct module dependencies (imports) for a file."""

    name = "list_dependencies"
    description = (
        "List direct internal module dependencies (imports) and external NPM package "
        "dependencies for a given file from the repository graph."
    )
    permission = "read"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Exact file path in repo."},
            "file": {"type": "string", "description": "Alias for path."},
        },
    }

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        file_path = args.get("path") or args.get("file") or ""
        data = graph_list_dependencies(ctx.graph, file=file_path)
        is_ok = "error" not in data
        if ctx.files is not None:
            try:
                if ctx.files.get_changes():
                    data["note"] = "graph reflects original commit"
            except Exception:
                pass
        return ToolResult(
            ok=is_ok,
            data=data,
            error=data.get("error") if not is_ok else None,
            summary=f"list_dependencies {file_path}",
        )


class ListDependentsTool(Tool):
    """List direct module dependents (importers) for a file."""

    name = "list_dependents"
    description = (
        "List direct importers (dependents) that import or re-export the specified file "
        "from the repository graph."
    )
    permission = "read"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Exact file path in repo."},
            "file": {"type": "string", "description": "Alias for path."},
        },
    }

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        file_path = args.get("path") or args.get("file") or ""
        data = graph_list_dependents(ctx.graph, file=file_path)
        is_ok = "error" not in data
        if ctx.files is not None:
            try:
                if ctx.files.get_changes():
                    data["note"] = "graph reflects original commit"
            except Exception:
                pass
        return ToolResult(
            ok=is_ok,
            data=data,
            error=data.get("error") if not is_ok else None,
            summary=f"list_dependents {file_path}",
        )


class BlastRadiusTool(Tool):
    """Compute transitive downstream blast radius impacts if a file is modified."""

    name = "blast_radius"
    description = (
        "Compute the transitive blast radius (impacted downstream files) if the specified "
        "file is modified, ordered by BFS distance depth."
    )
    permission = "read"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Exact file path in repo."},
            "file": {"type": "string", "description": "Alias for path."},
            "max_depth": {
                "type": "integer",
                "description": "Maximum BFS traversal depth. Defaults to 3.",
                "default": 3,
            },
        },
    }

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        file_path = args.get("path") or args.get("file") or ""
        depth = args.get("max_depth", 3)
        data = graph_blast_radius(ctx.graph, file=file_path, max_depth=depth)
        is_ok = "error" not in data
        if ctx.files is not None:
            try:
                if ctx.files.get_changes():
                    data["note"] = "graph reflects original commit"
            except Exception:
                pass
        return ToolResult(
            ok=is_ok,
            data=data,
            error=data.get("error") if not is_ok else None,
            summary=f"blast_radius {file_path} (total: {data.get('total', 0)})",
        )


class ListFilesTool(Tool):
    """List repository files from the effective working copy tree with statuses."""

    name = "list_files"
    description = (
        "List repository files from the effective tree (reflecting working-copy modifications, "
        "additions, and deletions) with file statuses and sizes."
    )
    permission = "read"
    parameters = {
        "type": "object",
        "properties": {
            "dir": {
                "type": "string",
                "description": "Optional subdirectory filter (e.g. 'src/').",
                "default": "",
            },
        },
    }

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        raw_dir = (args.get("dir") or "").strip().replace("\\", "/").strip("/")
        tree: list[dict[str, Any]] = []

        if ctx.files is not None:
            try:
                tree = ctx.files.list_files_tree()
            except Exception as exc:
                return ToolResult(
                    ok=False,
                    data={"error": f"Failed to list files: {exc}"},
                    error=f"Failed to list files: {exc}",
                    summary=f"list_files '{raw_dir}' (error)",
                )
        elif ctx.source_dir is not None and ctx.source_dir.exists():
            for p in sorted(ctx.source_dir.rglob("*")):
                if p.is_file() and p.name != ".ingest_version":
                    rel = p.relative_to(ctx.source_dir).as_posix()
                    tree.append(
                        {
                            "path": rel,
                            "status": "unchanged",
                            "graph_node": rel in ctx.graph,
                            "size": p.stat().st_size,
                        }
                    )
        else:
            for n in sorted(ctx.graph.nodes):
                tree.append(
                    {
                        "path": n,
                        "status": "unchanged",
                        "graph_node": True,
                        "size": 0,
                    }
                )

        if raw_dir:
            prefix = f"{raw_dir}/"
            filtered = [
                item for item in tree if item["path"] == raw_dir or item["path"].startswith(prefix)
            ]
        else:
            filtered = tree

        return ToolResult(
            ok=True,
            data={
                "dir": raw_dir,
                "files": filtered,
                "total": len(filtered),
            },
            summary=f"list_files '{raw_dir}' ({len(filtered)} items)",
        )


class ReadFileTool(Tool):
    """Read line-bounded, line-numbered source code from effective working copy."""

    name = "read_file"
    description = (
        "Read lines from an effective repository file. Capped at 300 lines and 12,000 characters "
        "per call. Returns line numbers and untrusted-data wrapped content."
    )
    permission = "read"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Exact file path in repo."},
            "file": {"type": "string", "description": "Alias for path."},
            "start": {
                "type": "integer",
                "description": "1-based starting line number. Defaults to 1.",
                "default": 1,
            },
            "end": {
                "type": "integer",
                "description": "1-based ending line number. Defaults to 200.",
                "default": 200,
            },
        },
    }

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        file_path = args.get("path") or args.get("file") or ""
        if not file_path:
            return ToolResult(
                ok=False,
                data={"error": "File path must be provided."},
                error="File path must be provided.",
                summary="read_file (missing path)",
            )

        start = args.get("start", 1)
        end = args.get("end", 200)

        if ctx.files is not None:
            try:
                norm = normalize_path(file_path)
            except Exception as exc:
                return ToolResult(
                    ok=False,
                    data={"error": f"Invalid path '{file_path}': {exc}"},
                    error=f"Invalid path '{file_path}': {exc}",
                    summary=f"read_file {file_path} (invalid path)",
                )

            try:
                eff = ctx.files.read_effective(norm)
                raw_text = eff["content"]
            except Exception as exc:
                return ToolResult(
                    ok=False,
                    data={"error": str(exc)},
                    error=str(exc),
                    summary=f"read_file {norm} (not found)",
                )

            lines = raw_text.splitlines()
            total_lines = len(lines)
            start_line = max(1, int(start))
            end_line = max(start_line, int(end))
            if end_line - start_line + 1 > 300:
                end_line = start_line + 299

            selected_lines = lines[start_line - 1 : end_line]
            actual_end_line = min(start_line + len(selected_lines) - 1, total_lines)
            formatted_lines = [
                f"{start_line + idx}: {line}" for idx, line in enumerate(selected_lines)
            ]
            content_str = "\n".join(formatted_lines)
            truncated = False
            if len(content_str) > 12000:
                content_str = content_str[:12000] + "\n[truncated]"
                truncated = True

            wrapped = wrap_untrusted(content_str, kind="source_code")
            return ToolResult(
                ok=True,
                data={
                    "file": norm,
                    "path": norm,
                    "start_line": start_line,
                    "end_line": actual_end_line,
                    "total_lines": total_lines,
                    "content": wrapped,
                    "truncated": truncated,
                },
                summary=f"read_file {norm} (L{start_line}-L{actual_end_line})",
            )
        else:
            # Fallback for graph_tools direct calls without files service
            res = graph_read_file(
                graph=ctx.graph,
                file=file_path,
                source_dir=ctx.source_dir,
                start=start,
                end=end,
            )
            is_ok = "error" not in res
            return ToolResult(
                ok=is_ok,
                data=res,
                error=res.get("error") if not is_ok else None,
                summary=f"read_file {file_path}",
            )


class SearchCodeTool(Tool):
    """Search for text or regular expressions across effective repository text files."""

    name = "search_code"
    description = (
        "Search text contents across effective repository files. Regex pattern length is capped "
        "at 200 characters to prevent ReDoS. Maximum results capped at 50."
    )
    permission = "read"
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Text substring or regex pattern to search for.",
            },
            "regex": {
                "type": "boolean",
                "description": "Whether query is a regular expression. Defaults to false.",
                "default": False,
            },
            "max_results": {
                "type": "integer",
                "description": "Max results to return (capped at 50). Defaults to 50.",
                "default": 50,
            },
        },
        "required": ["query"],
    }

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        query = args.get("query", "")
        if not query:
            return ToolResult(
                ok=True,
                data={"query": "", "matches": [], "total": 0},
                summary="search_code '' (0 matches)",
            )

        if len(query) > 200:
            return ToolResult(
                ok=False,
                data={"error": "Search pattern exceeds maximum length of 200 characters."},
                error="Search pattern exceeds maximum length of 200 characters.",
                summary="search_code (pattern too long)",
            )

        is_regex = bool(args.get("regex", False))
        max_results = min(max(1, int(args.get("max_results", 50))), 50)

        compiled_regex: re.Pattern[str] | None = None
        if is_regex:
            try:
                compiled_regex = re.compile(query, re.MULTILINE)
            except re.error as r_err:
                return ToolResult(
                    ok=False,
                    data={"error": f"Invalid regex pattern: {r_err}"},
                    error=f"Invalid regex pattern: {r_err}",
                    summary="search_code (invalid regex)",
                )

        # Collect files to scan
        files_to_scan: list[str] = []
        if ctx.files is not None:
            try:
                tree = ctx.files.list_files_tree()
                files_to_scan = [item["path"] for item in tree if item.get("status") != "deleted"]
            except Exception:
                pass
        elif ctx.source_dir is not None and ctx.source_dir.exists():
            for p in sorted(ctx.source_dir.rglob("*")):
                if p.is_file() and p.name != ".ingest_version":
                    files_to_scan.append(p.relative_to(ctx.source_dir).as_posix())
        else:
            files_to_scan = sorted(list(ctx.graph.nodes))

        matches: list[dict[str, Any]] = []

        for file_path in files_to_scan:
            if len(matches) >= max_results:
                break

            content: str | None = None
            if ctx.files is not None:
                try:
                    eff = ctx.files.read_effective(file_path)
                    content = eff["content"]
                except Exception:
                    continue
            elif ctx.source_dir is not None:
                target = ctx.source_dir / file_path
                if not target.is_file():
                    continue
                try:
                    content = target.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
            else:
                continue

            if not content:
                continue

            lines = content.splitlines()
            file_match_count = 0
            for line_no, line in enumerate(lines, start=1):
                if file_match_count >= 10:  # Per-file match cap
                    break
                if len(matches) >= max_results:
                    break

                matched = False
                if compiled_regex:
                    if compiled_regex.search(line):
                        matched = True
                else:
                    if query.lower() in line.lower():
                        matched = True

                if matched:
                    matches.append(
                        {
                            "path": file_path,
                            "line": line_no,
                            "preview": line.strip()[:150],
                        }
                    )
                    file_match_count += 1

        return ToolResult(
            ok=True,
            data={
                "query": query,
                "matches": matches,
                "total": len(matches),
                "capped": len(matches) >= max_results,
            },
            summary=f"search_code '{query}' ({len(matches)} matches)",
        )


class TranslateTextTool(Tool):
    """Translate natural language text using the Phase 9 translation engine."""

    name = "translate_text"
    description = "Translate text or comments into a target language using the BodhCode engine."
    permission = "read"
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Text to translate."},
            "target_language": {
                "type": "string",
                "description": "Target language code or name (e.g. 'hi', 'te', 'es', 'fr').",
            },
        },
        "required": ["text", "target_language"],
    }

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        text = args.get("text", "")
        target_lang = args.get("target_language", "en")

        if not text.strip():
            return ToolResult(
                ok=True,
                data={"translated_text": "", "target_language": target_lang},
                summary=f"translate_text ({target_lang})",
            )

        if ctx.session is None:
            return ToolResult(
                ok=False,
                data={"error": "Database session required for translation caching."},
                error="Database session required for translation caching.",
                summary=f"translate_text ({target_lang}) (no session)",
            )

        res = await i18n_translate_text(
            text=text,
            source=None,
            target=target_lang,
            kind="comment",
            session=ctx.session,
        )

        return ToolResult(
            ok=res.ok,
            data={
                "translated_text": res.text,
                "source_lang": res.source_lang,
                "target_lang": res.target_lang,
                "from_cache": res.from_cache,
                "ok": res.ok,
            },
            error=res.reason if not res.ok else None,
            summary=f"translate_text to {target_lang}",
        )


class UseSkillTool(Tool):
    """Stub tool for skills (Phase 13)."""

    name = "use_skill"
    description = "Execute a specialized domain skill (available in Phase 13)."
    permission = "read"
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Skill name."},
            "args": {
                "type": "object",
                "description": "Skill arguments.",
                "default": {},
            },
        },
        "required": ["name"],
    }

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        skill_name = args.get("name", "unknown")
        return ToolResult(
            ok=False,
            data={"error": "Skills are not available yet (scheduled for Phase 13)."},
            error="Skills are not available yet (scheduled for Phase 13).",
            summary=f"use_skill {skill_name} (stub: not available)",
        )


class FindFilesTool(Tool):
    """Fuzzy/substring search for valid file nodes in repository graph."""

    name = "find_files"
    description = (
        "Search for valid file paths in the repository using case-insensitive substring "
        "or fuzzy matching."
    )
    permission = "read"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query or partial name."},
            "limit": {
                "type": "integer",
                "description": "Maximum number of results to return (max 20).",
                "default": 20,
            },
        },
        "required": ["query"],
    }

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        q = args.get("query", "")
        lim = args.get("limit", 20)
        data = graph_find_files(ctx.graph, query=q, limit=lim)
        return ToolResult(
            ok=True,
            data=data,
            summary=f"find_files '{q}' ({len(data.get('matches', []))} matches)",
        )


class GetFileExportsTool(Tool):
    """Retrieve named exports and default export status for a file."""

    name = "get_file_exports"
    description = "Retrieve the named export symbols and default export status for a given file."
    permission = "read"
    parameters = {
        "type": "object",
        "properties": {
            "file": {"type": "string", "description": "Exact file path in repo."},
            "path": {"type": "string", "description": "Alias for file."},
        },
    }

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        file_path = args.get("file") or args.get("path") or ""
        data = graph_get_file_exports(ctx.graph, file=file_path)
        is_ok = "error" not in data
        return ToolResult(
            ok=is_ok,
            data=data,
            error=data.get("error") if not is_ok else None,
            summary=f"get_file_exports {file_path}",
        )
