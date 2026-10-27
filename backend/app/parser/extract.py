"""Pure AST fact extraction for TypeScript and JavaScript source files."""

import codecs

import tree_sitter_javascript as ts_js
import tree_sitter_typescript as ts_ts
from tree_sitter import Language, Node, Parser

from app.parser.types import FileFacts, ImportRef

# Maximum file size for AST analysis: 1 MB
MAX_SOURCE_BYTES = 1_000_000

# Module-level lazy language cache
_LANGUAGES: dict[str, Language] = {}


def _get_parser(lang_key: str) -> Parser:
    """Retrieve or initialize Parser instance for given language key."""
    if lang_key not in _LANGUAGES:
        if lang_key == "typescript":
            lang = Language(ts_ts.language_typescript())
        elif lang_key == "tsx":
            lang = Language(ts_ts.language_tsx())
        elif lang_key == "javascript":
            lang = Language(ts_js.language())
        else:
            raise ValueError(f"Unsupported grammar language: {lang_key}")
        _LANGUAGES[lang_key] = lang
    return Parser(_LANGUAGES[lang_key])


def _node_bytes(node: Node, source: bytes) -> bytes:
    """Safely slice source bytes for a node without C tree-sitter pointer dereferencing."""
    return source[node.start_byte : node.end_byte]


def _node_text(node: Node, source: bytes) -> str:
    """Safely slice and decode UTF-8 string for a node."""
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _extract_string_literal(node: Node, source: bytes) -> str | None:
    """Extract decoded string literal content without quotes, or None if non-literal / invalid."""
    if node.type == "string":
        parts: list[str] = []
        for child in node.children:
            if child.type in ('"', "'"):
                continue
            if child.type == "string_fragment":
                parts.append(_node_text(child, source))
            elif child.type == "escape_sequence":
                try:
                    decoded = codecs.decode(_node_bytes(child, source), "unicode_escape")
                    parts.append(decoded)
                except Exception:
                    return None
            else:
                return None
        return "".join(parts)

    if node.type == "template_string":
        parts = []
        for child in node.children:
            if child.type == "`":
                continue
            if child.type == "string_fragment":
                parts.append(_node_text(child, source))
            elif child.type == "escape_sequence":
                try:
                    decoded = codecs.decode(_node_bytes(child, source), "unicode_escape")
                    parts.append(decoded)
                except Exception:
                    return None
            elif child.type == "template_substitution":
                # Template substitutions with ${...} are non-literal dynamic arguments
                return None
            else:
                return None
        return "".join(parts)

    return None


def _is_all_type_named_imports(named_imports: Node) -> bool:
    """Check if every specifier in named_imports has the 'type' modifier."""
    specifiers = [c for c in named_imports.children if c.type == "import_specifier"]
    if not specifiers:
        return False
    return all(any(c.type == "type" for c in spec.children) for spec in specifiers)


def _extract_export_names(node: Node, source: bytes) -> list[str]:
    """Extract local named exported symbols from an export declaration."""
    names: list[str] = []
    for child in node.children:
        if child.type in ("function_declaration", "class_declaration", "enum_declaration"):
            name_node = child.child_by_field_name("name")
            if not name_node:
                for c in child.children:
                    if c.type in ("identifier", "type_identifier"):
                        name_node = c
                        break
            if name_node and name_node.start_byte < name_node.end_byte:
                names.append(_node_text(name_node, source))

        elif child.type in ("lexical_declaration", "variable_declaration"):
            for decl in child.children:
                if decl.type == "variable_declarator":
                    name_node = decl.child_by_field_name("name")
                    if not name_node:
                        for c in decl.children:
                            if c.type == "identifier":
                                name_node = c
                                break
                    if name_node and name_node.start_byte < name_node.end_byte:
                        names.append(_node_text(name_node, source))

        elif child.type in ("interface_declaration", "type_alias_declaration", "internal_module"):
            name_node = child.child_by_field_name("name")
            if not name_node:
                for c in child.children:
                    if c.type in ("identifier", "type_identifier"):
                        name_node = c
                        break
            if name_node and name_node.start_byte < name_node.end_byte:
                names.append(_node_text(name_node, source))

        elif child.type == "export_clause":
            for spec in child.children:
                if spec.type == "export_specifier":
                    alias_node = spec.child_by_field_name("alias")
                    name_node = spec.child_by_field_name("name")
                    if alias_node and alias_node.start_byte < alias_node.end_byte:
                        alias_name = _node_text(alias_node, source)
                        if alias_name != "default":
                            names.append(alias_name)
                    elif name_node and name_node.start_byte < name_node.end_byte:
                        id_name = _node_text(name_node, source)
                        if id_name != "default":
                            names.append(id_name)
                    else:
                        identifiers = [
                            _node_text(c, source)
                            for c in spec.children
                            if c.type == "identifier" and c.start_byte < c.end_byte
                        ]
                        if identifiers:
                            target = identifiers[-1]
                            if target != "default":
                                names.append(target)

        elif child.type == "namespace_export":
            for c in child.children:
                if c.type == "identifier" and c.start_byte < c.end_byte:
                    names.append(_node_text(c, source))
                    break

    return names


def extract_file(path: str, source: bytes) -> FileFacts:
    """Extract imports, exports, and call facts from TS/JS source code."""
    # Route by extension
    path_lower = path.lower()
    if path_lower.endswith(".tsx"):
        lang_key = "tsx"
    elif path_lower.endswith((".ts", ".mts", ".cts", ".d.ts")):
        lang_key = "typescript"
    elif path_lower.endswith((".js", ".jsx", ".mjs", ".cjs")):
        lang_key = "javascript"
    else:
        return FileFacts(
            path=path,
            imports=(),
            exports=(),
            has_default_export=False,
            unresolved_dynamic=0,
            flags=("skipped_unsupported",),
        )

    # Enforce size ceiling for supported source files
    if len(source) > MAX_SOURCE_BYTES:
        return FileFacts(
            path=path,
            imports=(),
            exports=(),
            has_default_export=False,
            unresolved_dynamic=0,
            flags=("skipped_large",),
        )

    parser = _get_parser(lang_key)
    tree = parser.parse(source)

    flags_list: list[str] = []
    if tree.root_node.has_error:
        flags_list.append("parse_error")

    imports_list: list[ImportRef] = []
    exports_list: list[str] = []
    has_default_export = False
    unresolved_dynamic = 0

    # TreeCursor-based AST walk (zero heap churn, memory safe)
    cursor = tree.walk()
    reached_root = False
    while not reached_root:
        node = cursor.node
        node_type = node.type
        descend = True

        # 1. Standard import statement
        if node_type == "import_statement":
            descend = False
            line = node.start_point.row + 1

            # Check for TS import x = require("...")
            import_require = next(
                (c for c in node.children if c.type == "import_require_clause"), None
            )
            if import_require:
                str_node = next((c for c in import_require.children if c.type == "string"), None)
                if str_node:
                    spec = _extract_string_literal(str_node, source)
                    if spec is not None:
                        imports_list.append(
                            ImportRef(specifier=spec, kind="require", line=line, type_only=False)
                        )
            else:
                source_node = node.child_by_field_name("source")
                if not source_node:
                    source_node = next((c for c in node.children if c.type == "string"), None)

                if source_node:
                    spec = _extract_string_literal(source_node, source)
                    if spec is not None:
                        # Determine if type_only
                        type_only = any(c.type == "type" for c in node.children)
                        if not type_only:
                            clause = next(
                                (c for c in node.children if c.type == "import_clause"), None
                            )
                            if clause:
                                if any(c.type == "type" for c in clause.children):
                                    type_only = True
                                else:
                                    named = next(
                                        (c for c in clause.children if c.type == "named_imports"),
                                        None,
                                    )
                                    others = [
                                        c
                                        for c in clause.children
                                        if c.type in ("identifier", "namespace_import")
                                    ]
                                    if named and not others:
                                        type_only = _is_all_type_named_imports(named)

                        imports_list.append(
                            ImportRef(
                                specifier=spec,
                                kind="import",
                                line=line,
                                type_only=type_only,
                            )
                        )

        # 2. Export statement (re-exports or declarations)
        elif node_type == "export_statement":
            descend = False
            line = node.start_point.row + 1
            source_node = node.child_by_field_name("source")
            if not source_node:
                source_node = next((c for c in node.children if c.type == "string"), None)

            is_default = any(c.type == "default" for c in node.children)
            if is_default:
                has_default_export = True

            # If it has a source, it's a re-export
            if source_node:
                spec = _extract_string_literal(source_node, source)
                if spec is not None:
                    type_only = any(c.type == "type" for c in node.children)
                    if not type_only:
                        export_clause = next(
                            (c for c in node.children if c.type == "export_clause"), None
                        )
                        if export_clause:
                            specifiers = [
                                c for c in export_clause.children if c.type == "export_specifier"
                            ]
                            if specifiers and all(
                                any(child.type == "type" for child in s.children)
                                for s in specifiers
                            ):
                                type_only = True

                    imports_list.append(
                        ImportRef(
                            specifier=spec,
                            kind="reexport",
                            line=line,
                            type_only=type_only,
                        )
                    )

            # Check for export { a as default }
            export_clause = next((c for c in node.children if c.type == "export_clause"), None)
            if export_clause:
                for s in export_clause.children:
                    if s.type == "export_specifier":
                        alias_node = s.child_by_field_name("alias")
                        if alias_node and _node_bytes(alias_node, source) == b"default":
                            has_default_export = True

            # Extract exported names if not default
            if not is_default:
                # `export * from` does not add names
                has_wildcard = any(c.type == "*" for c in node.children)
                if not (has_wildcard and source_node):
                    exports_list.extend(_extract_export_names(node, source))

        # 3. Call expressions: import(...) or require(...)
        elif node_type == "call_expression":
            line = node.start_point.row + 1
            fn_node = node.child_by_field_name("function")
            args_node = node.child_by_field_name("arguments")

            if fn_node and args_node:
                arg_exprs = [
                    c for c in args_node.children if c.type not in ("(", ")", ",", "comment")
                ]

                # Dynamic import(...)
                if fn_node.type == "import":
                    if arg_exprs:
                        spec = _extract_string_literal(arg_exprs[0], source)
                        if spec is not None:
                            imports_list.append(
                                ImportRef(
                                    specifier=spec,
                                    kind="dynamic",
                                    line=line,
                                    type_only=False,
                                )
                            )
                        else:
                            unresolved_dynamic += 1
                    else:
                        unresolved_dynamic += 1

                # require(...)
                elif fn_node.type == "identifier" and _node_bytes(fn_node, source) == b"require":
                    # Only treat require as a call to the bare identifier require
                    if arg_exprs:
                        spec = _extract_string_literal(arg_exprs[0], source)
                        if spec is not None:
                            imports_list.append(
                                ImportRef(
                                    specifier=spec,
                                    kind="require",
                                    line=line,
                                    type_only=False,
                                )
                            )
                        else:
                            unresolved_dynamic += 1
                    else:
                        unresolved_dynamic += 1

        if descend and cursor.goto_first_child():
            continue
        if cursor.goto_next_sibling():
            continue
        while True:
            if not cursor.goto_parent():
                reached_root = True
                break
            if cursor.goto_next_sibling():
                break

    # Sort outputs deterministically
    sorted_imports = tuple(sorted(imports_list, key=lambda x: (x.line, x.specifier, x.kind)))
    sorted_exports = tuple(sorted(set(exports_list)))

    return FileFacts(
        path=path,
        imports=sorted_imports,
        exports=sorted_exports,
        has_default_export=has_default_export,
        unresolved_dynamic=unresolved_dynamic,
        flags=tuple(sorted(flags_list)),
    )
