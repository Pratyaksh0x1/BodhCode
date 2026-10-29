"""Resource cleanup sweep and disk quota LRU cache management."""

from __future__ import annotations

import logging
import os
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlmodel import Session, col, select

from app.models.push import PushPreview
from app.models.repo import Repo
from app.models.translation import TranslationCache

logger = logging.getLogger(__name__)

DEFAULT_DATA_QUOTA_BYTES = 5 * 1024 * 1024 * 1024  # 5 GB


def cleanup_sweep(session: Session) -> dict[str, int]:
    """Execute scheduled database cleanup sweep.

    - Deletes expired unconfirmed PushPreview rows older than 1 hour past expiration.
    - Deletes TranslationCache entries older than 30 days.
    - Resets repos stuck in 'fetching' or 'analyzing' > 30 minutes to 'error' (timeout).
    """
    now = datetime.now(UTC)

    # 1. Clean expired unconsumed push previews
    preview_cutoff = now - timedelta(hours=1)
    preview_stmt = select(PushPreview).where(
        PushPreview.expires_at < preview_cutoff,
        PushPreview.consumed_at.is_(None),  # type: ignore[union-attr]
    )
    expired_previews = session.exec(preview_stmt).all()
    preview_count = len(expired_previews)
    for p in expired_previews:
        session.delete(p)

    # 2. Clean translation cache older than 30 days
    trans_cutoff = now - timedelta(days=30)
    trans_stmt = select(TranslationCache).where(TranslationCache.created_at < trans_cutoff)
    old_translations = session.exec(trans_stmt).all()
    trans_count = len(old_translations)
    for t in old_translations:
        session.delete(t)

    # 3. Reset stalled ingestion/analysis workers (> 30 min)
    stuck_cutoff = now - timedelta(minutes=30)
    stuck_stmt = select(Repo).where(
        col(Repo.status).in_(["fetching", "analyzing"]),
        Repo.updated_at < stuck_cutoff,
    )
    stuck_repos = session.exec(stuck_stmt).all()
    stuck_count = len(stuck_repos)
    for r in stuck_repos:
        r.status = "error"
        r.error_code = "timeout"
        r.error_message = "Repository analysis timed out after 30 minutes of inactivity."
        r.updated_at = now
        session.add(r)

    session.commit()

    logger.info(
        "Cleanup sweep finished: removed %d previews, %d translations, reset %d stalled repos",
        preview_count,
        trans_count,
        stuck_count,
    )

    return {
        "previews_deleted": preview_count,
        "translations_deleted": trans_count,
        "stalled_repos_reset": stuck_count,
    }


def _get_dir_size(path: Path) -> int:
    """Calculate cumulative directory byte size."""
    total = 0
    try:
        for entry in os.scandir(path):
            if entry.is_file(follow_symlinks=False):
                total += entry.stat(follow_symlinks=False).st_size
            elif entry.is_dir(follow_symlinks=False):
                total += _get_dir_size(Path(entry.path))
    except (FileNotFoundError, PermissionError):
        pass
    return total


def evict_repo_cache_lru(
    data_dir: Path,
    max_bytes: int = DEFAULT_DATA_QUOTA_BYTES,
    session: Session | None = None,
) -> list[str]:
    """Enforce disk storage quota on cached repositories using LRU eviction.

    Deletes commit directories in DATA_DIR/repos/{owner}/{name}/{commit_sha}/
    starting from least recently used / modified.
    Exempts repositories currently in 'fetching' or 'analyzing' state.
    Keeps the DB row and graphDoc intact.
    """
    repos_root = data_dir / "repos"
    if not repos_root.exists():
        return []

    # Identify repos protected from eviction
    protected_repos: set[str] = set()
    if session is not None:
        active_stmt = select(Repo).where(col(Repo.status).in_(["fetching", "analyzing"]))
        for r in session.exec(active_stmt).all():
            protected_repos.add(f"{r.owner}/{r.name}".lower())

    # Find all commit directory leaves: repos/{owner}/{name}/{commit_sha}
    candidates: list[tuple[float, int, Path, str]] = []
    total_disk_usage = 0

    for owner_entry in os.scandir(repos_root):
        if not owner_entry.is_dir():
            continue
        for name_entry in os.scandir(owner_entry.path):
            if not name_entry.is_dir():
                continue
            repo_slug = f"{owner_entry.name}/{name_entry.name}".lower()

            for commit_entry in os.scandir(name_entry.path):
                if not commit_entry.is_dir():
                    continue

                commit_path = Path(commit_entry.path)
                dir_size = _get_dir_size(commit_path)
                total_disk_usage += dir_size

                # If protected by active analysis/fetching, do not consider for eviction
                if repo_slug in protected_repos:
                    continue

                mtime = commit_entry.stat().st_mtime
                candidates.append((mtime, dir_size, commit_path, repo_slug))

    if total_disk_usage <= max_bytes:
        return []

    # Sort oldest first (lowest mtime)
    candidates.sort(key=lambda c: c[0])

    evicted_paths: list[str] = []
    bytes_to_free = total_disk_usage - max_bytes
    bytes_freed = 0

    for _mtime, size, commit_path, _slug in candidates:
        if bytes_freed >= bytes_to_free:
            break

        try:
            shutil.rmtree(commit_path, ignore_errors=True)
            bytes_freed += size
            evicted_paths.append(str(commit_path))
            logger.info("Evicted cached repo commit %s (%d bytes)", commit_path, size)
        except Exception as exc:
            logger.warning("Failed to evict %s: %s", commit_path, exc)

    return evicted_paths
