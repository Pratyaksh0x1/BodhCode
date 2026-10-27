"""Repository natural language resolution and detection for outgoing push operations."""

import logging
from pathlib import Path

from sqlmodel import Session

from app.config import get_settings
from app.github.client import GitHubClient
from app.i18n.detect import detect_language
from app.models.repo import Repo

logger = logging.getLogger(__name__)


def _find_local_readme(repo: Repo) -> str:
    """Attempt to read README text from cloned source repository on disk."""
    if not repo.commit_sha:
        return ""
    try:
        settings = get_settings()
        base = Path(settings.DATA_DIR) / "repos" / repo.owner / repo.name
        source_dir = base / repo.commit_sha / "src"
        if not source_dir.exists():
            return ""
        for name in ("README.md", "readme.md", "README", "readme.markdown", "README.txt"):
            candidate = source_dir / name
            if candidate.is_file():
                return candidate.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        logger.debug(f"Could not read local README for {repo.owner}/{repo.name}: {exc}")
    return ""


async def get_repo_language(
    repo: Repo,
    session: Session | None = None,
    token: str | None = None,
    github_client: GitHubClient | None = None,
) -> str:
    """Determine the primary natural language of the repository.

    Resolution precedence:
    1. push_language_override (if set by user)
    2. source_language (if previously detected in Phase 9)
    3. Detect now from README + recent issues/PRs + recent commits (lingua >= 0.6)
    4. Fallback to "en".
    """
    if repo.push_language_override:
        return repo.push_language_override

    if repo.source_language:
        return repo.source_language

    # Collect sample text for detection
    text_samples: list[str] = []

    # 1. Local README
    local_readme = _find_local_readme(repo)
    if local_readme:
        text_samples.append(local_readme[:3000])

    # 2. Remote GitHub content if client or token available
    if not text_samples and (github_client or token):
        try:
            if github_client:
                client_ctx = github_client
                should_close = False
            else:
                client_ctx = GitHubClient(token)
                should_close = True

            try:
                # Try fetching remote README if local wasn't found
                readme_data = await client_ctx.get_readme(repo.owner, repo.name, repo.branch)
                if readme_data and readme_data.get("content"):
                    text_samples.append(readme_data["content"][:3000])
            except Exception:
                pass

            try:
                # Fetch recent issues / PRs
                issues_data = await client_ctx.list_issues(
                    repo.owner, repo.name, page=1, per_page=20
                )
                for item in issues_data.get("items", []):
                    title = item.get("title", "")
                    body = item.get("body") or ""
                    if title:
                        text_samples.append(title)
                    if body:
                        text_samples.append(body[:500])
            except Exception:
                pass

            if should_close:
                await client_ctx.close()
        except Exception as exc:
            logger.debug(f"Remote language sample collection failed: {exc}")

    combined_text = "\n\n".join(text_samples).strip()
    if combined_text:
        detection = detect_language(combined_text)
        if detection.code and detection.confidence >= 0.6:
            if session is not None:
                try:
                    repo.source_language = detection.code
                    repo.source_language_confidence = detection.confidence
                    session.add(repo)
                    session.commit()
                    session.refresh(repo)
                except Exception as exc:
                    logger.warning(f"Failed to persist detected repo language: {exc}")
                    session.rollback()
            return detection.code

    return "en"
