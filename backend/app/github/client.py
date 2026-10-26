"""GitHub API HTTP client with error mapping and secure streaming download."""

from pathlib import Path
from typing import Any

import httpx

from app.github.limits import MAX_REPO_KB


class GitHubClientError(Exception):
    """Base exception for GitHub client errors."""

    pass


class RepoNotFound(GitHubClientError):
    """Repository not found or is private."""

    pass


class TokenInvalid(GitHubClientError):
    """GitHub OAuth token is invalid or expired."""

    pass


class RateLimited(GitHubClientError):
    """GitHub API rate limit was exceeded."""

    def __init__(self, reset_at: str | None = None) -> None:
        self.reset_at = reset_at
        super().__init__(
            f"GitHub API rate limit exceeded. Reset timestamp: {reset_at or 'unknown'}"
        )


class RepoTooLarge(GitHubClientError):
    """Repository exceeds allowed size limit."""

    pass


class GitHubError(GitHubClientError):
    """General GitHub API error."""

    pass


class GitHubClient:
    """Async client for interacting with the GitHub REST API."""

    def __init__(self, token: str) -> None:
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "bodhcode",
        }
        self.client = httpx.AsyncClient(
            base_url="https://api.github.com",
            headers=self.headers,
            timeout=30.0,
        )

    async def aclose(self) -> None:
        """Close the underlying HTTP client session."""
        await self.client.aclose()

    async def __aenter__(self) -> "GitHubClient":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.aclose()

    def _handle_response_status(self, response: httpx.Response) -> None:
        """Map HTTP error status codes to typed exceptions."""
        if response.status_code == 404:
            raise RepoNotFound("Repo not found, or it is private — only public repos are supported")
        if response.status_code == 401:
            raise TokenInvalid("GitHub token is invalid or expired")
        if (
            response.status_code in (403, 429)
            and response.headers.get("x-ratelimit-remaining") == "0"
        ):
            reset_at = response.headers.get("x-ratelimit-reset")
            raise RateLimited(reset_at=reset_at)
        if response.status_code >= 400:
            raise GitHubError(f"GitHub API request failed with status {response.status_code}")

    async def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        """Perform an API request and return parsed JSON body."""
        response = await self.client.request(method, url, **kwargs)
        self._handle_response_status(response)
        return response.json()

    async def get_repo(self, owner: str, name: str) -> dict[str, Any]:
        """Fetch repository metadata."""
        return await self._request("GET", f"/repos/{owner}/{name}")

    async def get_branch_sha(self, owner: str, name: str, ref: str) -> str:
        """Resolve a branch, tag, or commit reference to a 40-character commit SHA."""
        if len(ref) == 40 and all(c in "0123456789abcdefABCDEF" for c in ref):
            return ref.lower()

        data = await self._request("GET", f"/repos/{owner}/{name}/commits/{ref}")
        sha = data.get("sha")
        if not sha:
            raise GitHubError(f"Failed to resolve commit SHA for reference '{ref}'")
        return str(sha).lower()

    async def get_tree(self, owner: str, name: str, sha: str) -> dict[str, Any]:
        """Fetch recursive git tree for a given commit SHA."""
        return await self._request("GET", f"/repos/{owner}/{name}/git/trees/{sha}?recursive=1")

    async def download_zipball(
        self,
        owner: str,
        name: str,
        sha: str,
        dest_path: Path,
        max_bytes: int = MAX_REPO_KB * 1024,
    ) -> int:
        """Stream repository zipball to disk, enforcing size limits during transfer."""
        url = f"/repos/{owner}/{name}/zipball/{sha}"
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        downloaded = 0
        try:
            async with self.client.stream("GET", url, follow_redirects=True) as response:
                self._handle_response_status(response)

                # Ensure redirect host is only GitHub
                final_host = response.url.host
                if final_host not in ("github.com", "codeload.github.com", "api.github.com"):
                    raise GitHubError(f"Disallowed redirect host: '{final_host}'")

                with open(dest_path, "wb") as f:
                    async for chunk in response.aiter_bytes():
                        downloaded += len(chunk)
                        if downloaded > max_bytes:
                            raise RepoTooLarge(
                                f"Repository archive exceeded size limit ({max_bytes} bytes)"
                            )
                        f.write(chunk)
            return downloaded
        except Exception:
            if dest_path.exists():
                dest_path.unlink(missing_ok=True)
            raise
