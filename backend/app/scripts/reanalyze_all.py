"""One-off resumable and rate-limit friendly re-analysis script for stored repositories."""

import argparse
import asyncio
import sys
import time

from sqlmodel import Session, select

from app import db
from app.models.graph import RepoGraph
from app.models.repo import Repo
from app.parser.graph import PARSER_VERSION
from app.services.analyze import analyze_repo


async def reanalyze_all(delay: float = 0.1, limit: int | None = None, force: bool = False) -> int:
    """Iterate through repositories in the database and re-run analysis if invalid."""
    with Session(db.engine) as session:
        statement = select(Repo).order_by(Repo.id)
        if limit is not None and limit > 0:
            statement = statement.limit(limit)
        repos = list(session.exec(statement).all())

    total = len(repos)
    print(f"Found {total} repository record(s) in database.")
    if total == 0:
        print("No repositories to reanalyze.")
        return 0

    reanalyzed = 0
    skipped = 0
    failed = 0

    for idx, repo in enumerate(repos, start=1):
        repo_id = repo.id
        assert repo_id is not None
        repo_desc = f"{repo.owner}/{repo.name} (id={repo_id})"

        if not repo.commit_sha:
            print(f"[{idx}/{total}] SKIP: {repo_desc} - no commit_sha (not fetched).")
            skipped += 1
            continue

        # Check existing graph version for resumability
        if not force:
            with Session(db.engine) as session:
                graph = session.exec(
                    select(RepoGraph).where(
                        RepoGraph.repo_id == repo_id,
                        RepoGraph.commit_sha == repo.commit_sha,
                        RepoGraph.parser_version == PARSER_VERSION,
                    )
                ).first()
                if graph is not None:
                    print(
                        f"[{idx}/{total}] SKIP: {repo_desc} - already valid "
                        f"(parser v{PARSER_VERSION})."
                    )
                    skipped += 1
                    continue

        print(f"[{idx}/{total}] REANALYZE: {repo_desc} at commit {repo.commit_sha[:7]}...")
        try:
            await analyze_repo(repo_id)
            # Verify status
            with Session(db.engine) as session:
                refreshed = session.get(Repo, repo_id)
                if refreshed and refreshed.status == "ready":
                    count = refreshed.file_count
                    print(f"[{idx}/{total}] SUCCESS: {repo_desc} is ready ({count} nodes).")
                    reanalyzed += 1
                else:
                    err_msg = refreshed.error_message if refreshed else "unknown"
                    st = refreshed.status if refreshed else "missing"
                    print(f"[{idx}/{total}] ERROR: {repo_desc} status={st}: {err_msg}")
                    failed += 1
        except Exception as err:
            print(f"[{idx}/{total}] ERROR: {repo_desc} raised exception: {err}")
            failed += 1

        if delay > 0 and idx < total:
            time.sleep(delay)

    print("\n--- Summary ---")
    print(f"Total: {total} | Reanalyzed: {reanalyzed} | Skipped: {skipped} | Failed: {failed}")
    return 0 if failed == 0 else 1


def main() -> None:
    """Parse CLI arguments and run reanalyze_all."""
    parser = argparse.ArgumentParser(
        prog="python -m app.scripts.reanalyze_all",
        description="Re-run dependency analysis for repositories in database.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.1,
        help="Delay in seconds between repos to prevent rate limiting (default: 0.1s)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of repositories to process",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-analysis even if graph is already valid at current parser version",
    )

    args = parser.parse_args()
    exit_code = asyncio.run(reanalyze_all(delay=args.delay, limit=args.limit, force=args.force))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
