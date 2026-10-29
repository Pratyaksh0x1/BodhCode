"""Immutable, JSON-serializable dataclasses for AST extraction and module resolution."""

from dataclasses import dataclass
from typing import Literal

ImportKind = Literal["import", "reexport", "dynamic", "require"]
ResolutionKind = Literal["file", "external", "builtin", "unresolved"]


@dataclass(frozen=True)
class ImportRef:
    """Reference to an import or require statement within a file."""

    specifier: str
    kind: ImportKind
    line: int
    type_only: bool


@dataclass(frozen=True)
class FileFacts:
    """Extracted semantic facts for a single source file."""

    path: str
    imports: tuple[ImportRef, ...]
    exports: tuple[str, ...]
    has_default_export: bool
    unresolved_dynamic: int
    flags: tuple[str, ...]


@dataclass(frozen=True)
class Resolution:
    """Result of resolving an import specifier."""

    kind: ResolutionKind
    target: str | None = None
    package: str | None = None


@dataclass(frozen=True)
class ResolvedImport:
    """An import reference paired with its concrete resolution."""

    ref: ImportRef
    resolution: Resolution


@dataclass(frozen=True)
class AnalyzedFile:
    """Complete analysis result of a single file, containing facts and resolved imports."""

    path: str
    facts: FileFacts
    resolved_imports: tuple[ResolvedImport, ...]
    size: int = 0
