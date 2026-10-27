"""Versioned prompt templates for grounded file explanation."""

from typing import Any, Final

from app.ai.untrusted import UNTRUSTED_NOTICE, wrap_untrusted

PROMPT_VERSION: Final[int] = 1

EXPLAIN_SYSTEM_PROMPT: Final[str] = (
    "You are a repository architecture expert narrator. "
    "Your task is to explain a file's role in the codebase in 5–8 sentences for a developer "
    "new to the repository.\n\n"
    "CRITICAL CONSTRAINTS:\n"
    "1. Use ONLY the provided verified facts and source code.\n"
    "2. Mention which files depend on it and the architectural risk of changing it "
    "(based on the blast radius impact count and dependents).\n"
    "3. Refer to files ONLY by their exact paths provided in the facts. Never invent or assume "
    "files, imports, or relationships.\n"
    "4. If something is unknown or not evident from the facts, explicitly say so.\n"
    "5. Write your entire explanation in {language}.\n"
    "6. {untrusted_notice}"
)


def build_explain_messages(
    *,
    file_path: str,
    language: str,
    context_facts: dict[str, Any],
    source_code: str | None,
) -> list[dict[str, str]]:
    """Construct versioned system and user messages for file explanation."""
    system_content = EXPLAIN_SYSTEM_PROMPT.format(
        language=language,
        untrusted_notice=UNTRUSTED_NOTICE,
    )

    deps = ", ".join(context_facts.get("dependencies", [])) or "None"
    importers = ", ".join(context_facts.get("dependents", [])) or "None"
    pkgs = ", ".join(context_facts.get("external_deps", [])) or "None"
    blast = context_facts.get("blast_radius_total", 0)

    facts_lines = [
        f"- File Path: {file_path}",
        f"- Size: {context_facts.get('size', 0)} bytes",
        f"- Named Exports: {', '.join(context_facts.get('exports', [])) or 'None'}",
        f"- Has Default Export: {context_facts.get('has_default_export', False)}",
        f"- Direct Dependencies (imports): {deps}",
        f"- Direct Dependents (importers): {importers}",
        f"- External Packages: {pkgs}",
        f"- Transitive Blast Radius Impact Total: {blast} files",
        f"- Is Part of Circular Dependency: {context_facts.get('is_in_cycle', False)}",
        f"- Fan-In (in-degree): {context_facts.get('fan_in', 0)}",
        f"- Fan-Out (out-degree): {context_facts.get('fan_out', 0)}",
    ]
    facts_block = "\n".join(facts_lines)

    user_parts = [
        f"Verified Architectural Facts for `{file_path}`:\n{facts_block}",
    ]

    if source_code:
        wrapped_source = wrap_untrusted(source_code, kind="source_code")
        user_parts.append(f"Source Code Preview:\n{wrapped_source}")
    else:
        user_parts.append("Source Code: (not available)")

    user_parts.append(
        f"Please explain `{file_path}`'s role, dependencies, and risk in {language}."
    )

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]
