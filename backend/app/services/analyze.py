"""Repository analysis background job and graph persistence orchestrator."""

import logging
from pathlib import Path

from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool

from app import db
from app.config import get_settings
from app.models.graph import RepoGraph
from app.models.repo import Repo
from app.models.user import utc_now
from app.parser.analyze import analyze_repo_files
from app.parser.graph import (
    PARSER_VERSION,
    GraphDoc,
    GraphTooLargeError,
    RepoMeta,
    build_graph,
)

logger = logging.getLogger(__name__)

# Maximum total source bytes allowed in memory during analysis: 100 MB
MAX_ANALYSIS_TOTAL_BYTES = 100_000_000


def _mark_analyzing_or_skip(repo_id: int) -> tuple[Repo | None, bool]:
    """Check if valid graph exists or mark repo as analyzing."""
    with Session(db.engine) as session:
        repo = session.get(Repo, repo_id)
        if not repo:
            return None, False

        if not repo.commit_sha:
            repo.status = "failed"
            repo.error_code = "analyze_failed"
            repo.error_message = "Repository commit SHA is missing. Please ingest first."
            repo.updated_at = utc_now()
            session.add(repo)
            session.commit()
            return None, False

        # If valid graph already exists, skip directly to ready
        statement = select(RepoGraph).where(
            RepoGraph.repo_id == repo_id,
            RepoGraph.commit_sha == repo.commit_sha,
            RepoGraph.parser_version == PARSER_VERSION,
        )
        existing_valid = session.exec(statement).first()
        if existing_valid is not None:
            repo.status = "ready"
            repo.file_count = existing_valid.node_count
            repo.error_code = None
            repo.error_message = None
            repo.updated_at = utc_now()
            session.add(repo)
            session.commit()
            return repo, True

        repo.status = "analyzing"
        repo.error_code = None
        repo.error_message = None
        repo.updated_at = utc_now()
        session.add(repo)
        session.commit()
        session.refresh(repo)
        return repo, False


def _load_files_and_build_graph(owner: str, name: str, commit_sha: str) -> GraphDoc:
    """Read extracted files from disk and execute deterministic graph building."""
    settings = get_settings()
    target_dir = Path(settings.DATA_DIR) / "repos" / owner / name / commit_sha / "src"

    if not target_dir.exists():
        raise FileNotFoundError(f"Source repository files not found at {target_dir}")

    files: dict[str, bytes] = {}
    total_bytes = 0

    for p in target_dir.rglob("*"):
        if p.is_file() and p.name != ".ingest_version":
            file_size = p.stat().st_size
            total_bytes += file_size
            if total_bytes > MAX_ANALYSIS_TOTAL_BYTES:
                raise ValueError("Repository source files exceed maximum analysis limit (100 MB)")
            rel_posix = p.relative_to(target_dir).as_posix()
            files[rel_posix] = p.read_bytes()

    analyzed = analyze_repo_files(files)
    meta = RepoMeta(owner=owner, name=name, commit_sha=commit_sha)
    return build_graph(analyzed, meta)


def _save_graph_and_mark_ready(repo_id: int, commit_sha: str, graph_doc: GraphDoc) -> None:
    """Persist RepoGraph and transition Repo status to ready."""
    with Session(db.engine) as session:
        repo = session.get(Repo, repo_id)
        if not repo:
            return

        statement = select(RepoGraph).where(
            RepoGraph.repo_id == repo.id,
            RepoGraph.commit_sha == commit_sha,
        )
        existing_graph = session.exec(statement).first()

        json_payload = graph_doc.to_json()
        if existing_graph is not None:
            existing_graph.parser_version = PARSER_VERSION
            existing_graph.graph_json = json_payload
            existing_graph.node_count = graph_doc.stats.files
            existing_graph.edge_count = graph_doc.stats.edges
            existing_graph.created_at = utc_now()
            session.add(existing_graph)
        else:
            new_graph = RepoGraph(
                repo_id=repo.id,
                commit_sha=commit_sha,
                parser_version=PARSER_VERSION,
                graph_json=json_payload,
                node_count=graph_doc.stats.files,
                edge_count=graph_doc.stats.edges,
                created_at=utc_now(),
            )
            session.add(new_graph)

        repo.status = "ready"
        repo.file_count = graph_doc.stats.files
        repo.error_code = None
        repo.error_message = None
        repo.updated_at = utc_now()
        session.add(repo)
        session.commit()


def _mark_analyze_failure(repo_id: int, error_code: str, error_message: str) -> None:
    """Transition Repo to failed status with error code and user-safe message."""
    with Session(db.engine) as session:
        repo = session.get(Repo, repo_id)
        if repo:
            repo.status = "failed"
            repo.error_code = error_code
            repo.error_message = error_message
            repo.updated_at = utc_now()
            session.add(repo)
            session.commit()


async def analyze_repo(repo_id: int) -> None:
    """Background task to analyze repository dependencies and persist canonical graph."""
    repo, is_already_valid = await run_in_threadpool(_mark_analyzing_or_skip, repo_id)
    if repo is None or is_already_valid:
        return

    owner = repo.owner
    name = repo.name
    commit_sha = repo.commit_sha
    assert commit_sha is not None

    try:
        graph_doc = await run_in_threadpool(_load_files_and_build_graph, owner, name, commit_sha)
        await run_in_threadpool(_save_graph_and_mark_ready, repo_id, commit_sha, graph_doc)
    except GraphTooLargeError as err:
        logger.warning(f"Graph limits exceeded for repo {repo_id}: {err}")
        await run_in_threadpool(
            _mark_analyze_failure,
            repo_id,
            "graph_too_large",
            "Dependency graph exceeds safety limits (maximum 5,000 nodes or 20,000 edges).",
        )
    except Exception as err:
        logger.error(f"Analysis failed for repo {repo_id}: {err}", exc_info=True)
        await run_in_threadpool(
            _mark_analyze_failure,
            repo_id,
            "analyze_failed",
            "An error occurred while analyzing repository dependencies.",
        )
