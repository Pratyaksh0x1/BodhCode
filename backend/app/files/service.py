"""File service managing read-only original repo files and per-user working copies."""

import hashlib
import json
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from app.config import get_settings
from app.files.errors import (
    BinaryFileNotSupported,
    FileNotFound,
    FileTooLarge,
    InvalidPath,
    PreconditionFailed,
    RepoFilesUnavailable,
)
from app.models.files import WorkingFile
from app.models.graph import RepoGraph
from app.models.repo import Repo
from app.models.user import User, utc_now

LANGUAGE_HINTS: dict[str, str] = {
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".d.ts": "typescript",
    ".json": "json",
    ".css": "css",
    ".scss": "scss",
    ".html": "html",
    ".md": "markdown",
    ".mdx": "markdown",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".toml": "toml",
    ".svg": "xml",
    ".xml": "xml",
    ".txt": "plaintext",
}


def normalize_path(p: str) -> str:
    """Normalize and validate a file path.

    Rules:
    - POSIX forward slashes only.
    - No leading slash.
    - No directory traversal ('..').
    - No backslashes.
    - No null bytes.
    - Maximum length 300 characters.
    - No segments named '.git'.
    """
    if not isinstance(p, str):
        raise InvalidPath("Path must be a string")
    if not p or not p.strip():
        raise InvalidPath("Path cannot be empty or whitespace")
    if "\x00" in p:
        raise InvalidPath("Null bytes are not allowed in path")
    if "\\" in p:
        raise InvalidPath("Backslashes are not allowed; use POSIX forward slashes")
    if len(p) > 300:
        raise InvalidPath("Path exceeds maximum length of 300 characters")
    if p.startswith("/"):
        raise InvalidPath("Leading slashes are not allowed")

    parts = p.split("/")

    clean_parts: list[str] = []
    for part in parts:
        if part == "" or part == ".":
            continue
        if part == "..":
            raise InvalidPath("Directory traversal ('..') is not allowed")
        if part.lower() == ".git":
            raise InvalidPath("Access to '.git' segments is not allowed")
        clean_parts.append(part)

    if not clean_parts:
        raise InvalidPath("Path cannot resolve to empty")

    return "/".join(clean_parts)


def get_language_hint(path: str) -> str:
    """Infer Monaco language identifier from path extension."""
    lower = path.lower()
    if lower.endswith(".d.ts"):
        return "typescript"
    for ext, lang in LANGUAGE_HINTS.items():
        if lower.endswith(ext):
            return lang
    return "plaintext"


def compute_content_hash(content: str) -> str:
    """Compute deterministic SHA-256 hex digest of string content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def get_repo_source_dir(repo: Repo) -> Path:
    """Locate source directory on disk for the repository."""
    settings = get_settings()
    commit_sha = repo.commit_sha
    if not commit_sha:
        raise RepoFilesUnavailable("Repository commit SHA is not resolved")
    source_dir = Path(settings.DATA_DIR) / "repos" / repo.owner / repo.name / commit_sha / "src"
    if not source_dir.exists():
        raise RepoFilesUnavailable(
            f"Repository source files are not available at {source_dir}. "
            "Please refresh the repository."
        )
    return source_dir.resolve()


def resolve_original_path(repo: Repo, path: str) -> tuple[Path, Path]:
    """Resolve file path within repository directory with strict containment check."""
    normalized = normalize_path(path)
    base_dir = get_repo_source_dir(repo)
    target = (base_dir / normalized).resolve()

    try:
        target.relative_to(base_dir)
    except ValueError:
        raise InvalidPath("Path escapes repository directory") from None

    return base_dir, target


def read_original(repo: Repo, path: str) -> str:
    """Read file content from original repository extraction directory."""
    _, target = resolve_original_path(repo, path)
    if not target.exists() or not target.is_file():
        raise FileNotFound(f"Original file '{path}' not found")

    size = target.stat().st_size
    if size > 1_000_000:
        raise FileTooLarge(f"File '{path}' size ({size} bytes) exceeds limit of 1,000,000 bytes")

    raw_bytes = target.read_bytes()
    if b"\x00" in raw_bytes:
        raise BinaryFileNotSupported(f"File '{path}' contains null bytes and is binary")

    try:
        return raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise BinaryFileNotSupported(f"File '{path}' is not valid UTF-8 text") from None


def read_effective(user: User, repo: Repo, path: str, session: Session) -> dict[str, Any]:
    """Read effective file content (working copy if modified, else original)."""
    normalized = normalize_path(path)

    statement = select(WorkingFile).where(
        WorkingFile.user_id == user.id,
        WorkingFile.repo_id == repo.id,
        WorkingFile.path == normalized,
    )
    working = session.exec(statement).first()

    if working is not None:
        if working.is_deleted:
            raise FileNotFound(f"File '{normalized}' has been deleted in your working copy")

        status = "added" if working.is_new else "modified"
        content = working.content
        size = len(content.encode("utf-8"))
        content_hash = compute_content_hash(content)
        return {
            "path": normalized,
            "content": content,
            "language_hint": get_language_hint(normalized),
            "status": status,
            "size": size,
            "hash": content_hash,
            "content_hash": content_hash,
            "base_hash": working.base_hash,
        }

    content = read_original(repo, normalized)
    size = len(content.encode("utf-8"))
    content_hash = compute_content_hash(content)
    return {
        "path": normalized,
        "content": content,
        "language_hint": get_language_hint(normalized),
        "status": "unchanged",
        "size": size,
        "hash": content_hash,
        "content_hash": content_hash,
        "base_hash": content_hash,
    }


def write_file(
    user: User,
    repo: Repo,
    path: str,
    content: str,
    session: Session,
    if_match: str | None = None,
) -> dict[str, Any]:
    """Write file to user working copy. If content matches original, removes working copy row."""
    normalized = normalize_path(path)

    if "\x00" in content:
        raise BinaryFileNotSupported("Content contains null bytes")
    content_bytes = content.encode("utf-8")
    if len(content_bytes) > 1_000_000:
        raise FileTooLarge(
            f"Content size ({len(content_bytes)} bytes) exceeds limit of 1,000,000 bytes"
        )

    current_statement = select(WorkingFile).where(
        WorkingFile.user_id == user.id,
        WorkingFile.repo_id == repo.id,
        WorkingFile.path == normalized,
    )
    working = session.exec(current_statement).first()

    current_hash: str | None = None
    if working is not None:
        if not working.is_deleted:
            current_hash = compute_content_hash(working.content)
    else:
        try:
            orig = read_original(repo, normalized)
            current_hash = compute_content_hash(orig)
        except FileNotFound:
            current_hash = None

    if if_match is not None:
        cleaned_match = if_match.strip().strip('"')
        if cleaned_match != current_hash:
            raise PreconditionFailed(
                f"If-Match '{cleaned_match}' does not match current hash '{current_hash}'"
            )

    original_exists = False
    original_content: str | None = None
    try:
        original_content = read_original(repo, normalized)
        original_exists = True
    except FileNotFound:
        original_exists = False

    new_hash = compute_content_hash(content)

    if original_exists:
        assert original_content is not None
        if content == original_content:
            # Content equals original: delete working row (no-op edit)
            if working is not None:
                session.delete(working)
                session.commit()
            return {
                "path": normalized,
                "status": "unchanged",
                "hash": new_hash,
                "size": len(content_bytes),
            }

        orig_hash = compute_content_hash(original_content)
        if working is None:
            working = WorkingFile(
                user_id=user.id,
                repo_id=repo.id,
                path=normalized,
                content=content,
                is_new=False,
                is_deleted=False,
                base_hash=orig_hash,
                updated_at=utc_now(),
            )
            session.add(working)
        else:
            working.content = content
            working.is_new = False
            working.is_deleted = False
            working.base_hash = orig_hash
            working.updated_at = utc_now()
            session.add(working)

        session.commit()
        session.refresh(working)
        return {
            "path": normalized,
            "status": "modified",
            "hash": new_hash,
            "content_hash": new_hash,
            "size": len(content_bytes),
        }

    # New file (not in original repo extraction)
    if working is None:
        working = WorkingFile(
            user_id=user.id,
            repo_id=repo.id,
            path=normalized,
            content=content,
            is_new=True,
            is_deleted=False,
            base_hash=None,
            updated_at=utc_now(),
        )
        session.add(working)
    else:
        working.content = content
        working.is_new = True
        working.is_deleted = False
        working.base_hash = None
        working.updated_at = utc_now()
        session.add(working)

    session.commit()
    session.refresh(working)
    return {
        "path": normalized,
        "status": "added",
        "hash": new_hash,
        "content_hash": new_hash,
        "size": len(content_bytes),
    }


def delete_file(user: User, repo: Repo, path: str, session: Session) -> str:
    """Mark file deleted in working copy or remove working row for newly added file."""
    normalized = normalize_path(path)

    statement = select(WorkingFile).where(
        WorkingFile.user_id == user.id,
        WorkingFile.repo_id == repo.id,
        WorkingFile.path == normalized,
    )
    working = session.exec(statement).first()

    original_exists = False
    original_hash: str | None = None
    try:
        orig = read_original(repo, normalized)
        original_exists = True
        original_hash = compute_content_hash(orig)
    except FileNotFound:
        original_exists = False

    if not original_exists and working is None:
        raise FileNotFound(f"File '{normalized}' not found to delete")

    if not original_exists:
        if working is not None:
            session.delete(working)
            session.commit()
        return "deleted"

    if working is None:
        working = WorkingFile(
            user_id=user.id,
            repo_id=repo.id,
            path=normalized,
            content="",
            is_new=False,
            is_deleted=True,
            base_hash=original_hash,
            updated_at=utc_now(),
        )
        session.add(working)
    else:
        working.content = ""
        working.is_new = False
        working.is_deleted = True
        working.base_hash = original_hash
        working.updated_at = utc_now()
        session.add(working)

    session.commit()
    return "deleted"


def revert_file(user: User, repo: Repo, path: str, session: Session) -> bool:
    """Revert user working file changes by deleting the working copy row."""
    normalized = normalize_path(path)
    statement = select(WorkingFile).where(
        WorkingFile.user_id == user.id,
        WorkingFile.repo_id == repo.id,
        WorkingFile.path == normalized,
    )
    working = session.exec(statement).first()
    if working is not None:
        session.delete(working)
        session.commit()
        return True
    return False


def diff_for(user: User, repo: Repo, path: str, session: Session) -> dict[str, str]:
    """Compute original and modified content for diff comparison view."""
    normalized = normalize_path(path)
    statement = select(WorkingFile).where(
        WorkingFile.user_id == user.id,
        WorkingFile.repo_id == repo.id,
        WorkingFile.path == normalized,
    )
    working = session.exec(statement).first()

    original = ""
    try:
        original = read_original(repo, normalized)
    except FileNotFound:
        original = ""

    if working is None:
        return {
            "path": normalized,
            "status": "unchanged",
            "original": original,
            "modified": original,
        }

    if working.is_deleted:
        return {
            "path": normalized,
            "status": "deleted",
            "original": original,
            "modified": "",
        }

    if working.is_new:
        return {
            "path": normalized,
            "status": "added",
            "original": "",
            "modified": working.content,
        }

    return {
        "path": normalized,
        "status": "modified",
        "original": original,
        "modified": working.content,
    }


def rename_file(
    user: User,
    repo: Repo,
    old_path: str,
    new_path: str,
    session: Session,
) -> dict[str, Any]:
    """Rename a file in the working copy (implemented as delete + add)."""
    norm_old = normalize_path(old_path)
    norm_new = normalize_path(new_path)
    effective = read_effective(user, repo, norm_old, session)
    delete_file(user, repo, norm_old, session)
    return write_file(user, repo, norm_new, effective["content"], session)


def list_tree(user: User, repo: Repo, session: Session) -> list[dict[str, Any]]:
    """Generate merged tree of original files and working copy changes."""
    graph_nodes: set[str] = set()
    graph_statement = select(RepoGraph).where(
        RepoGraph.repo_id == repo.id,
        RepoGraph.commit_sha == repo.commit_sha,
    )
    repo_graph = session.exec(graph_statement).first()
    if repo_graph and repo_graph.graph_json:
        try:
            g_doc = json.loads(repo_graph.graph_json)
            for node in g_doc.get("nodes", []):
                if "id" in node:
                    graph_nodes.add(node["id"])
        except Exception:
            pass

    source_dir: Path | None = None
    try:
        source_dir = get_repo_source_dir(repo)
    except RepoFilesUnavailable:
        source_dir = None

    items: dict[str, dict[str, Any]] = {}

    if source_dir and source_dir.exists():
        for p in source_dir.rglob("*"):
            if p.is_file() and p.name != ".ingest_version":
                rel = p.relative_to(source_dir).as_posix()
                items[rel] = {
                    "path": rel,
                    "status": "unchanged",
                    "graph_node": rel in graph_nodes,
                    "size": p.stat().st_size,
                }

    working_statement = select(WorkingFile).where(
        WorkingFile.user_id == user.id,
        WorkingFile.repo_id == repo.id,
    )
    working_rows = session.exec(working_statement).all()

    for wf in working_rows:
        if wf.is_deleted:
            if wf.path in items:
                items[wf.path]["status"] = "deleted"
            else:
                items[wf.path] = {
                    "path": wf.path,
                    "status": "deleted",
                    "graph_node": wf.path in graph_nodes,
                    "size": 0,
                }
        elif wf.is_new:
            items[wf.path] = {
                "path": wf.path,
                "status": "added",
                "graph_node": wf.path in graph_nodes,
                "size": len(wf.content.encode("utf-8")),
            }
        else:
            if wf.path in items:
                items[wf.path]["status"] = "modified"
                items[wf.path]["size"] = len(wf.content.encode("utf-8"))
            else:
                items[wf.path] = {
                    "path": wf.path,
                    "status": "modified",
                    "graph_node": wf.path in graph_nodes,
                    "size": len(wf.content.encode("utf-8")),
                }

    return [items[k] for k in sorted(items.keys())]


def get_changes(user: User, repo: Repo, session: Session) -> list[dict[str, Any]]:
    """List all working copy changed files with their status."""
    statement = (
        select(WorkingFile)
        .where(
            WorkingFile.user_id == user.id,
            WorkingFile.repo_id == repo.id,
        )
        .order_by(WorkingFile.path)
    )
    working_rows = session.exec(statement).all()
    results: list[dict[str, Any]] = []
    for wf in working_rows:
        status = "deleted" if wf.is_deleted else ("added" if wf.is_new else "modified")
        results.append(
            {
                "path": wf.path,
                "status": status,
                "updated_at": wf.updated_at.isoformat(),
            }
        )
    return results


class BoundFileService:
    """File service bound to a specific user, repo, and session."""

    def __init__(self, user: User, repo: Repo, session: Session) -> None:
        self.user = user
        self.repo = repo
        self.session = session

    def read_effective(self, path: str) -> dict[str, Any]:
        return read_effective(self.user, self.repo, path, self.session)

    def write_file(self, path: str, content: str, if_match: str | None = None) -> dict[str, Any]:
        return write_file(self.user, self.repo, path, content, self.session, if_match=if_match)

    def delete_file(self, path: str) -> str:
        return delete_file(self.user, self.repo, path, self.session)

    def revert_file(self, path: str) -> bool:
        return revert_file(self.user, self.repo, path, self.session)

    def diff_for(self, path: str) -> dict[str, str]:
        return diff_for(self.user, self.repo, path, self.session)

    def rename_file(self, old_path: str, new_path: str) -> dict[str, Any]:
        return rename_file(self.user, self.repo, old_path, new_path, self.session)

    def list_files_tree(self) -> list[dict[str, Any]]:
        return list_tree(self.user, self.repo, self.session)

    def get_changes(self) -> list[dict[str, Any]]:
        return get_changes(self.user, self.repo, self.session)
