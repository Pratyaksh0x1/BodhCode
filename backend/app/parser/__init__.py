"""Pure AST parser, fact extraction, and module resolution for TS/JS repos."""

from app.parser.analyze import analyze_repo_files
from app.parser.extract import extract_file
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
    "AnalyzedFile",
    "FileFacts",
    "ImportKind",
    "ImportRef",
    "Resolution",
    "ResolutionKind",
    "ResolvedImport",
    "TsConfig",
    "TsConfigIndex",
    "analyze_repo_files",
    "extract_file",
    "load_tsconfigs",
    "parse_jsonc",
    "resolve",
]
