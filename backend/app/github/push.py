"""GitHub Git Data API write client for creating forks, branches, commits, PRs, and issues."""

import asyncio
import logging
import re
import time
from typing import Any

import httpx

from app.github.client import (
    GitHubClient,
    GitHubClientError,
    GitHubError,
    RateLimited,
    RepoNotFound,
    TokenInvalid,
)

logger = logging.getLogger(__name__)


class PermissionDenied(GitHubClientError):
    """Action was forbidden by GitHub permissions."""

    pass


class ValidationFailed(GitHubClientError):
    """GitHub rejected the payload with validation errors."""

    pass


class Conflict(GitHubClientError):
    """GitHub encountered a state conflict."""

    pass


def sanitize_github_message(text: str) -> str:
    """Sanitize GitHub error messages by removing potential sensitive parameters."""
    # Redact GitHub tokens (ghp_, gho_, github_pat_, etc.)
    sanitized = re.sub(r"gh[pousr]_[A-Za-z0-9_]+", "[REDACTED]", text)
    sanitized = re.sub(r"github_pat_[A-Za-z0-9_]+", "[REDACTED]", sanitized)
    sanitized = re.sub(
        r"(?:bearer|token)\s*[:= ]\s*[A-Za-z0-9_.-]+", "[REDACTED]", sanitized, flags=re.I
    )
    return sanitized.strip()[:300]


class GitHubPushClient(GitHubClient):
    """Extended client providing write operations via the Git Data API."""

    def _handle_response_status(self, response: httpx.Response) -> None:
        """Map HTTP error status codes to typed exceptions with zero secret leakage."""
        if response.status_code == 404:
            raise RepoNotFound("Repo not found, or it is private — only public repos are supported")
        if response.status_code == 401:
            raise TokenInvalid("GitHub token is invalid or expired")
        if response.status_code == 403:
            if response.headers.get("x-ratelimit-remaining") == "0":
                reset_at = response.headers.get("x-ratelimit-reset")
                raise RateLimited(reset_at=reset_at)
            raise PermissionDenied("Permission denied by GitHub")
        if response.status_code == 409:
            raise Conflict("Conflict occurred on GitHub (branch, ref, or object state conflict)")
        if response.status_code == 422:
            try:
                err_data = response.json()
                msg = err_data.get("message", "Validation failed on GitHub")
                errors = err_data.get("errors", [])
                if errors and isinstance(errors, list):
                    details = "; ".join(
                        str(e.get("message", e)) for e in errors if isinstance(e, dict)
                    )
                    if details:
                        msg = f"{msg}: {details}"
            except Exception:
                msg = "Validation failed on GitHub"
            raise ValidationFailed(sanitize_github_message(msg))
        if response.status_code >= 400:
            raise GitHubError(f"GitHub API request failed with status {response.status_code}")

    async def _post(self, url: str, json: dict[str, Any]) -> dict[str, Any]:
        """Send POST request and return JSON response."""
        response = await self.client.post(url, json=json)
        self._handle_response_status(response)
        return response.json()

    async def _patch(self, url: str, json: dict[str, Any]) -> dict[str, Any]:
        """Send PATCH request and return JSON response."""
        response = await self.client.patch(url, json=json)
        self._handle_response_status(response)
        return response.json()

    async def ensure_fork(
        self,
        owner: str,
        name: str,
        user_login: str,
    ) -> tuple[str, str]:
        """Verify push access or ensure a valid fork exists on user's GitHub account.

        Returns (target_owner, target_name).
        """
        repo_data = await self.get_repo(owner, name)
        perms = repo_data.get("permissions", {})
        if perms.get("push") is True:
            # User has direct write/push access to upstream repo
            return owner, name

        # Check if user already owns a fork
        try:
            fork_data = await self.get_repo(user_login, name)
            if fork_data.get("fork"):
                return user_login, name
        except RepoNotFound:
            pass

        # Create fork via POST /repos/{owner}/{name}/forks
        fork_resp = await self._post(f"/repos/{owner}/{name}/forks", json={})
        fork_owner = fork_resp.get("owner", {}).get("login", user_login)
        fork_name = fork_resp.get("name", name)

        # Poll fork readiness (max 60 seconds with backoff)
        start_time = time.time()
        delay = 1.0
        while time.time() - start_time < 60.0:
            try:
                check = await self.get_repo(fork_owner, fork_name)
                if check and check.get("id"):
                    return fork_owner, fork_name
            except RepoNotFound:
                pass
            await asyncio.sleep(delay)
            delay = min(delay * 1.5, 5.0)

        return fork_owner, fork_name

    async def create_branch(
        self,
        owner: str,
        name: str,
        branch: str,
        from_sha: str,
    ) -> dict[str, Any]:
        """Create a new git reference for branch.

        Idempotent: if ref already exists with matching name, returns existing ref.
        """
        ref_path = f"/repos/{owner}/{name}/git/refs/heads/{branch}"
        check_resp = await self.client.get(ref_path)
        if check_resp.status_code == 200:
            return check_resp.json()

        payload = {"ref": f"refs/heads/{branch}", "sha": from_sha}
        return await self._post(f"/repos/{owner}/{name}/git/refs", json=payload)

    async def create_blob(self, owner: str, name: str, content: str) -> str:
        """Create a Git blob object with UTF-8 encoding and return its SHA."""
        data = await self._post(
            f"/repos/{owner}/{name}/git/blobs",
            json={"content": content, "encoding": "utf-8"},
        )
        return str(data["sha"])

    async def create_tree(
        self,
        owner: str,
        name: str,
        base_tree: str,
        entries: list[dict[str, Any]],
    ) -> str:
        """Create a Git tree object based on base_tree with given entries."""
        data = await self._post(
            f"/repos/{owner}/{name}/git/trees",
            json={"base_tree": base_tree, "tree": entries},
        )
        return str(data["sha"])

    async def create_commit(
        self,
        owner: str,
        name: str,
        message: str,
        tree: str,
        parents: list[str],
    ) -> str:
        """Create a Git commit referencing tree and parent commits."""
        data = await self._post(
            f"/repos/{owner}/{name}/git/commits",
            json={"message": message, "tree": tree, "parents": parents},
        )
        return str(data["sha"])

    async def update_ref(
        self,
        owner: str,
        name: str,
        branch: str,
        commit_sha: str,
    ) -> dict[str, Any]:
        """Fast-forward update branch reference to new commit SHA."""
        return await self._patch(
            f"/repos/{owner}/{name}/git/refs/heads/{branch}",
            json={"sha": commit_sha, "force": False},
        )

    async def open_pull_request(
        self,
        upstream_owner: str,
        upstream_name: str,
        head: str,
        base: str,
        title: str,
        body: str,
    ) -> dict[str, Any]:
        """Open a pull request from head to base.

        Idempotent: if an open PR with same head already exists, returns it.
        """
        # Check for existing open PR
        check_resp = await self.client.get(
            f"/repos/{upstream_owner}/{upstream_name}/pulls",
            params={"head": head, "state": "open"},
        )
        if check_resp.status_code == 200:
            existing = check_resp.json()
            if isinstance(existing, list) and len(existing) > 0:
                return existing[0]

        return await self._post(
            f"/repos/{upstream_owner}/{upstream_name}/pulls",
            json={"title": title, "body": body, "head": head, "base": base},
        )

    async def create_issue(
        self,
        owner: str,
        name: str,
        title: str,
        body: str,
    ) -> dict[str, Any]:
        """Create a new issue on the repository."""
        return await self._post(
            f"/repos/{owner}/{name}/issues",
            json={"title": title, "body": body},
        )

    async def create_comment(
        self,
        owner: str,
        name: str,
        number: int,
        body: str,
    ) -> dict[str, Any]:
        """Create a comment on an issue or pull request."""
        return await self._post(
            f"/repos/{owner}/{name}/issues/{number}/comments",
            json={"body": body},
        )
