"""Grounded file explanation orchestrator with caching and path verification."""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import networkx as nx
from pydantic import BaseModel
from sqlmodel import Session, select

from app.ai.llm import LLMClient, get_llm_client
from app.ai.prompts.explain import PROMPT_VERSION, build_explain_messages
from app.ai.tracing import traced
from app.ai.verify import annotate, extract_path_mentions, verify_mentions
from app.models.explain import ExplainCache
from app.models.repo import Repo
from app.parser.blast import blast_radius as blast_algo

logger = logging.getLogger(__name__)


class ExplainResult(BaseModel):
    """Grounded explanation response payload."""

    explanation: str
    verified_files: list[str]
    flagged: list[str]
    language: str
    cached: bool = False


def compute_explain_cache_key(
    commit_sha: str,
    file_path: str,
    language: str,
    prompt_version: int = PROMPT_VERSION,
) -> str:
    """Compute deterministic SHA-256 cache key."""
    raw = f"{commit_sha}|{file_path}|{language}|{prompt_version}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_file_context(graph: nx.DiGraph, file_path: str) -> dict[str, Any]:
    """Extract strictly verified architectural facts from the dependency graph."""
    node_data = graph.nodes[file_path]

    dependencies = sorted(graph.successors(file_path))
    dependents = sorted(graph.predecessors(file_path))
    external_deps = sorted(node_data.get("external_deps", []))

    # Transitive blast radius total
    impacts = blast_algo(graph, file_path, max_depth=None)
    blast_total = len(impacts)

    # Check cycle membership
    is_in_cycle = False
    for scc in nx.strongly_connected_components(graph):
        if len(scc) > 1 and file_path in scc:
            is_in_cycle = True
            break

    return {
        "size": node_data.get("size", 0),
        "exports": sorted(node_data.get("exports", [])),
        "has_default_export": bool(node_data.get("has_default_export", False)),
        "dependencies": dependencies,
        "dependents": dependents,
        "external_deps": external_deps,
        "blast_radius_total": blast_total,
        "is_in_cycle": is_in_cycle,
        "fan_in": graph.in_degree(file_path),
        "fan_out": graph.out_degree(file_path),
    }


def read_source_preview(source_dir: Path | None, file_path: str) -> str | None:
    """Read first 300 lines or 12,000 characters of the file safely."""
    if source_dir is None:
        return None

    resolved_base = source_dir.resolve()
    target_path = (source_dir / file_path).resolve()

    try:
        target_path.relative_to(resolved_base)
    except ValueError:
        return None

    if not target_path.is_file():
        return None

    try:
        raw_text = target_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    lines = raw_text.splitlines()[:300]
    preview = "\n".join(lines)
    if len(preview) > 12000:
        preview = preview[:12000] + "\n[truncated]"
    return preview


@traced(name="explain.file", run_type="chain")
async def explain_file(
    repo: Repo,
    file_path: str,
    language: str,
    graph: nx.DiGraph,
    source_dir: Path | None,
    session: Session,
    llm_client: LLMClient | None = None,
    refresh: bool = False,
) -> ExplainResult:
    """Explain a file's architectural role, verified against the dependency graph."""
    file_path = file_path.strip().replace("\\", "/")
    commit_sha = repo.commit_sha or "HEAD"

    cache_key = compute_explain_cache_key(
        commit_sha=commit_sha,
        file_path=file_path,
        language=language,
    )

    # 1. Cache hit check
    if not refresh:
        statement = select(ExplainCache).where(ExplainCache.key == cache_key)
        cached_entry = session.exec(statement).first()
        if cached_entry is not None:
            try:
                data = json.loads(cached_entry.response_json)
                return ExplainResult(
                    explanation=data["explanation"],
                    verified_files=data["verified_files"],
                    flagged=data["flagged"],
                    language=data["language"],
                    cached=True,
                )
            except Exception as exc:
                logger.warning("Failed to decode explain cache entry: %s", exc)

    # 2. Extract facts from graph
    context_facts = build_file_context(graph, file_path)
    source_preview = read_source_preview(source_dir, file_path)

    # 3. Construct prompt
    messages = build_explain_messages(
        file_path=file_path,
        language=language,
        context_facts=context_facts,
        source_code=source_preview,
    )

    # 4. LLM call
    client = llm_client or get_llm_client()
    llm_res = await client.chat(
        messages=messages,
        feature="explain",
        temperature=0.2,
        max_tokens=800,
        prompt_name="explain",
        prompt_version=PROMPT_VERSION,
    )

    raw_explanation = llm_res.text or ""

    # 5. Path verification
    mentions = extract_path_mentions(raw_explanation)
    verified_map, flagged_mentions = verify_mentions(mentions, graph)

    annotated_explanation = annotate(raw_explanation, flagged_mentions)
    verified_files = sorted(list(set(verified_map.values())))
    flagged_files = sorted(list(set(m.cleaned for m in flagged_mentions)))

    result = ExplainResult(
        explanation=annotated_explanation,
        verified_files=verified_files,
        flagged=flagged_files,
        language=language,
        cached=False,
    )

    # 6. Store in cache
    try:
        cache_item = ExplainCache(
            key=cache_key,
            commit_sha=commit_sha,
            file_path=file_path,
            language=language,
            prompt_version=PROMPT_VERSION,
            response_json=json.dumps(result.model_dump()),
        )
        session.merge(cache_item)
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.warning("Failed to save explanation to cache: %s", exc)

    return result
