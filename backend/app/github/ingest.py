import asyncio
import logging
from pathlib import Path

from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool

from app import db
from app.auth.crypto import get_github_token
from app.cleanup import evict_repo_cache_lru
from app.config import get_settings
from app.github.client import (
    GitHubClient,
    RateLimited,
    RepoNotFound,
    RepoTooLarge,
    TokenInvalid,
)
from app.github.extract import (
    TooManyFilesError,
    ZipBombError,
    extract_repo_archive,
)
from app.github.limits import INGEST_VERSION, MAX_REPO_KB
from app.models.repo import Repo
from app.models.user import User, utc_now

logger = logging.getLogger(__name__)

# Max 3 active repo ingestions system-wide
INGESTION_SEMAPHORE = asyncio.Semaphore(3)


def _get_repo_and_token(repo_id: int) -> tuple[Repo, str]:
    """Retrieve Repo and decrypt owner User's GitHub token in database session."""
    with Session(db.engine) as session:
        repo = session.get(Repo, repo_id)
        if not repo:
            raise ValueError(f"Repo {repo_id} not found")
        user = session.get(User, repo.user_id)
        if not user:
            raise ValueError(f"User for repo {repo_id} not found")
        token = get_github_token(user)

        repo.status = "fetching"
        repo.error_code = None
        repo.error_message = None
        repo.updated_at = utc_now()
        session.add(repo)
        session.commit()
        session.refresh(repo)
        return repo, token


def _update_repo_success(
    repo_id: int,
    commit_sha: str,
    branch: str,
    size_kb: int,
    file_count: int,
) -> None:
    """Update repo record to 'fetched' with metadata."""
    with Session(db.engine) as session:
        repo = session.get(Repo, repo_id)
        if repo:
            repo.status = "fetched"
            repo.commit_sha = commit_sha
            repo.branch = branch
            repo.default_branch_size_kb = size_kb
            repo.file_count = file_count
            repo.ingest_version = INGEST_VERSION
            repo.error_code = None
            repo.error_message = None
            repo.updated_at = utc_now()
            session.add(repo)
            session.commit()


def _update_repo_failure(repo_id: int, error_code: str, error_message: str) -> None:
    """Update repo record to 'failed' with user-safe error text."""
    with Session(db.engine) as session:
        repo = session.get(Repo, repo_id)
        if repo:
            repo.status = "failed"
            repo.error_code = error_code
            repo.error_message = error_message
            repo.updated_at = utc_now()
            session.add(repo)
            session.commit()


def sweep_stale_fetching_repos() -> int:
    """Reset any repos stuck in 'fetching' status at server startup back to 'queued'."""
    with Session(db.engine) as session:
        statement = select(Repo).where(Repo.status == "fetching")
        stale_repos = session.exec(statement).all()
        for repo in stale_repos:
            repo.status = "queued"
            repo.updated_at = utc_now()
            session.add(repo)
        session.commit()
        return len(stale_repos)


async def ingest_repo(repo_id: int) -> None:
    """Asynchronously ingest a repository source archive within safety limits."""
    async with INGESTION_SEMAPHORE:
        try:
            repo, token = await run_in_threadpool(_get_repo_and_token, repo_id)
        except Exception as err:
            logger.error(f"Failed to initialize ingestion for repo {repo_id}: {err}")
            return

        settings = get_settings()

        async with GitHubClient(token) as client:
            try:
                # 1. Fetch repo metadata and enforce size/privacy limits
                metadata = await client.get_repo(repo.owner, repo.name)
                if metadata.get("private"):
                    await run_in_threadpool(
                        _update_repo_failure,
                        repo_id,
                        "not_found",
                        "Repo not found, or it is private — only public repos are supported",
                    )
                    return

                size_kb = int(metadata.get("size", 0))
                if size_kb > MAX_REPO_KB:
                    await run_in_threadpool(
                        _update_repo_failure,
                        repo_id,
                        "too_large",
                        f"Repository size ({size_kb} KB) exceeds the limit of {MAX_REPO_KB} KB",
                    )
                    return

                # 2. Resolve default branch and commit SHA
                branch = repo.branch or metadata.get("default_branch", "main")
                commit_sha = await client.get_branch_sha(repo.owner, repo.name, branch)

                # 3. Target dir: DATA_DIR/repos/<owner>/<name>/<commit_sha>/src
                target_dir = (
                    Path(settings.DATA_DIR) / "repos" / repo.owner / repo.name / commit_sha / "src"
                )
                marker_file = target_dir / ".ingest_version"

                # Check shared cache reuse
                if target_dir.exists() and marker_file.exists():
                    try:
                        version_text = marker_file.read_text(encoding="utf-8").strip()
                        if version_text == str(INGEST_VERSION):
                            file_count = sum(
                                1
                                for p in target_dir.rglob("*")
                                if p.is_file() and p.name != ".ingest_version"
                            )
                            await run_in_threadpool(
                                _update_repo_success,
                                repo_id,
                                commit_sha,
                                branch,
                                size_kb,
                                file_count,
                            )
                            return
                    except Exception:
                        pass  # Re-download if cached marker read fails

                # 4. Download and extract safely
                temp_zip = (
                    Path(settings.DATA_DIR)
                    / "tmp"
                    / f"{repo.owner}_{repo.name}_{commit_sha[:8]}.zip"
                )
                temp_zip.parent.mkdir(parents=True, exist_ok=True)
                try:
                    await client.download_zipball(repo.owner, repo.name, commit_sha, temp_zip)
                    file_count = await run_in_threadpool(extract_repo_archive, temp_zip, target_dir)
                finally:
                    if temp_zip.exists():
                        temp_zip.unlink(missing_ok=True)

                # 5. Write cache marker and mark fetched
                marker_file.write_text(str(INGEST_VERSION), encoding="utf-8")
                await run_in_threadpool(
                    _update_repo_success,
                    repo_id,
                    commit_sha,
                    branch,
                    size_kb,
                    file_count,
                )

                # 6. Check disk quota after successful download
                try:
                    with Session(db.engine) as session:
                        evict_repo_cache_lru(Path(settings.DATA_DIR), session=session)
                except Exception as exc:
                    logger.warning("Cache quota eviction error: %s", exc)

            except RepoNotFound:
                await run_in_threadpool(
                    _update_repo_failure,
                    repo_id,
                    "not_found",
                    "Repo not found, or it is private — only public repos are supported",
                )
            except TokenInvalid:
                await run_in_threadpool(
                    _update_repo_failure,
                    repo_id,
                    "token_invalid",
                    "GitHub authentication failed. Please sign in again.",
                )
            except RateLimited as err:
                await run_in_threadpool(
                    _update_repo_failure,
                    repo_id,
                    "rate_limited",
                    str(err),
                )
            except RepoTooLarge as err:
                await run_in_threadpool(
                    _update_repo_failure,
                    repo_id,
                    "too_large",
                    str(err),
                )
            except TooManyFilesError as err:
                await run_in_threadpool(
                    _update_repo_failure,
                    repo_id,
                    "too_many_files",
                    str(err),
                )
            except ZipBombError:
                await run_in_threadpool(
                    _update_repo_failure,
                    repo_id,
                    "zip_bomb",
                    "Repository archive failed safety checks "
                    "(uncompressed size exceeded threshold)",
                )
            except Exception as err:
                logger.error(f"Ingestion failed for repo {repo_id}: {err}")
                await run_in_threadpool(
                    _update_repo_failure,
                    repo_id,
                    "ingest_error",
                    "An unexpected error occurred while fetching repository source files.",
                )
