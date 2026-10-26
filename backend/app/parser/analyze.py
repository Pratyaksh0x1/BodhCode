"""Pure orchestrator for repository AST extraction and import resolution."""

from collections.abc import Mapping

from app.parser.extract import extract_file
from app.parser.resolve import resolve
from app.parser.tsconfig import load_tsconfigs
from app.parser.types import AnalyzedFile, ResolvedImport


def analyze_repo_files(files: Mapping[str, bytes]) -> list[AnalyzedFile]:
    """Deterministically analyze repo files into facts and resolved imports.

    Pure function: zero I/O, zero network, zero database, zero LLM.
    """
    tsconfig_index = load_tsconfigs(files)
    all_files = frozenset(files.keys())

    results: list[AnalyzedFile] = []

    # Sort files deterministically by path
    for path in sorted(files.keys()):
        source = files[path]
        facts = extract_file(path, source)

        # Skip unsupported non-code extensions (e.g. .md, .png, .json)
        if "skipped_unsupported" in facts.flags:
            continue

        cfg = tsconfig_index.for_file(path)
        resolved_imports = tuple(
            ResolvedImport(
                ref=imp,
                resolution=resolve(path, imp.specifier, all_files, cfg),
            )
            for imp in facts.imports
        )

        results.append(
            AnalyzedFile(
                path=path,
                facts=facts,
                resolved_imports=resolved_imports,
            )
        )

    return results
