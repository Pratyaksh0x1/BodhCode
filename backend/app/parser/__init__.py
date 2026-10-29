"""Pure AST parser, fact extraction, and module resolution for TS/JS repos."""

from app.parser.analyze import analyze_repo_files
from app.parser.blast import (
    Impact,
    NodeNotFound,
    blast_radius,
    degree_stats,
    dependencies,
    dependents,
    find_cycles,
    to_digraph,
    walk,
)
from app.parser.extract import extract_file
from app.parser.graph import (
    PARSER_VERSION,
    EdgeDoc,
    FolderDoc,
    GraphDoc,
    GraphTooLargeError,
    NodeDoc,
    RepoMeta,
    StatsDoc,
    build_graph,
)
from app.parser.resolve import resolve
from app.parser.tsconfig import TsConfig, TsConfigIndex, load_tsconfigs, parse_jsonc
from app.parser.types import (
    AnalyzedFile,
    FileFacts,
    ImportKind,
    ImportRef,
    Resolution,
    ResolutionKind,
    ResolvedImport,
)

__all__ = [
    "PARSER_VERSION",
    "AnalyzedFile",
    "EdgeDoc",
    "FileFacts",
    "FolderDoc",
    "GraphDoc",
    "GraphTooLargeError",
    "Impact",
    "ImportKind",
    "ImportRef",
    "NodeDoc",
    "NodeNotFound",
    "RepoMeta",
    "Resolution",
    "ResolutionKind",
    "ResolvedImport",
    "StatsDoc",
    "TsConfig",
    "TsConfigIndex",
    "analyze_repo_files",
    "blast_radius",
    "build_graph",
    "degree_stats",
    "dependencies",
    "dependents",
    "extract_file",
    "find_cycles",
    "load_tsconfigs",
    "parse_jsonc",
    "resolve",
    "to_digraph",
    "walk",
]
