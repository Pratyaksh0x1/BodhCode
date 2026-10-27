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

    async def get_readme(
        self,
        owner: str,
        name: str,
        ref: str | None = None,
    ) -> dict[str, str]:
        """Fetch repository README raw markdown content and file name."""
        url = f"/repos/{owner}/{name}/readme"
        params = {"ref": ref} if ref else {}
        resp = await self.client.get(
            url,
            params=params,
            headers={"Accept": "application/vnd.github.raw+json"},
        )
        self._handle_response_status(resp)

        cd = resp.headers.get("content-disposition", "")
        file_name = "README.md"
        if "filename=" in cd:
            file_name = cd.split("filename=")[-1].strip("\"' ")

        # Support base64 JSON payload if returned instead of raw text
        if resp.headers.get("content-type", "").startswith("application/json"):
            try:
                data = resp.json()
                if (
                    isinstance(data, dict)
                    and "content" in data
                    and data.get("encoding") == "base64"
                ):
                    import base64

                    content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
                    return {"file_name": data.get("name", file_name), "content": content}
            except Exception:
                pass

        return {"file_name": file_name, "content": resp.text}

    @staticmethod
    def _sanitize_issue_or_pr(item: dict[str, Any]) -> dict[str, Any]:
        """Extract only UI-needed fields for issues or pull requests."""
        user = item.get("user") or {}
        labels = [
            {"name": lbl.get("name", ""), "color": lbl.get("color", "")}
            for lbl in item.get("labels", [])
            if isinstance(lbl, dict)
        ]
        return {
            "number": item.get("number"),
            "title": item.get("title", ""),
            "body": item.get("body") or "",
            "state": item.get("state", "open"),
            "author": {
                "login": user.get("login", "ghost"),
                "avatar_url": user.get("avatar_url", ""),
            },
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
            "labels": labels,
            "comment_count": item.get("comments", 0),
            "html_url": item.get("html_url", ""),
        }

    @staticmethod
    def _sanitize_comment(item: dict[str, Any]) -> dict[str, Any]:
        """Extract only UI-needed fields for issue or PR comments."""
        user = item.get("user") or {}
        return {
            "id": item.get("id"),
            "body": item.get("body") or "",
            "author": {
                "login": user.get("login", "ghost"),
                "avatar_url": user.get("avatar_url", ""),
            },
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
            "html_url": item.get("html_url", ""),
        }

    @staticmethod
    def _extract_next_page(
        link_header: str | None,
        page: int,
        item_count: int,
        per_page: int,
    ) -> int | None:
        """Extract next page integer from GitHub Link header or pagination count."""
        import re

        if link_header:
            match = re.search(r'page=(\d+)[^>]*>;\s*rel="next"', link_header)
            if match:
                return int(match.group(1))
        if item_count >= per_page:
            return page + 1
        return None

    async def list_issues(
        self,
        owner: str,
        name: str,
        state: str = "open",
        page: int = 1,
        per_page: int = 30,
    ) -> dict[str, Any]:
        """List repository issues, explicitly filtering out pull requests."""
        url = f"/repos/{owner}/{name}/issues"
        params = {"state": state, "page": page, "per_page": per_page}
        resp = await self.client.get(url, params=params)
        self._handle_response_status(resp)
        data = resp.json()
        if not isinstance(data, list):
            data = []

        # Filter out items carrying a 'pull_request' key
        pure_issues = [it for it in data if "pull_request" not in it]
        sanitized = [self._sanitize_issue_or_pr(it) for it in pure_issues]
        next_page = self._extract_next_page(
            resp.headers.get("link"),
            page,
            len(data),
            per_page,
        )

        return {"items": sanitized, "next_page": next_page}

    async def get_issue(self, owner: str, name: str, number: int) -> dict[str, Any]:
        """Fetch details for a single issue."""
        url = f"/repos/{owner}/{name}/issues/{number}"
        data = await self._request("GET", url)
        return self._sanitize_issue_or_pr(data)

    async def list_issue_comments(
        self,
        owner: str,
        name: str,
        number: int,
        page: int = 1,
        per_page: int = 30,
    ) -> dict[str, Any]:
        """List comments for an issue (or PR conversation comments)."""
        url = f"/repos/{owner}/{name}/issues/{number}/comments"
        params = {"page": page, "per_page": per_page}
        resp = await self.client.get(url, params=params)
        self._handle_response_status(resp)
        data = resp.json()
        if not isinstance(data, list):
            data = []

        sanitized = [self._sanitize_comment(it) for it in data]
        next_page = self._extract_next_page(
            resp.headers.get("link"),
            page,
            len(data),
            per_page,
        )
        return {"items": sanitized, "next_page": next_page}

    async def list_pulls(
        self,
        owner: str,
        name: str,
        state: str = "open",
        page: int = 1,
        per_page: int = 30,
    ) -> dict[str, Any]:
        """List pull requests for a repository."""
        url = f"/repos/{owner}/{name}/pulls"
        params = {"state": state, "page": page, "per_page": per_page}
        resp = await self.client.get(url, params=params)
        self._handle_response_status(resp)
        data = resp.json()
        if not isinstance(data, list):
            data = []

        sanitized = [self._sanitize_issue_or_pr(it) for it in data]
        next_page = self._extract_next_page(
            resp.headers.get("link"),
            page,
            len(data),
            per_page,
        )
        return {"items": sanitized, "next_page": next_page}

    async def get_pull(self, owner: str, name: str, number: int) -> dict[str, Any]:
        """Fetch details for a single pull request."""
        url = f"/repos/{owner}/{name}/pulls/{number}"
        data = await self._request("GET", url)
        return self._sanitize_issue_or_pr(data)

    async def list_pull_comments(
        self,
        owner: str,
        name: str,
        number: int,
        page: int = 1,
        per_page: int = 30,
    ) -> dict[str, Any]:
        """Fetch all comments for a PR by combining issue comments and review comments."""
        # 1. Fetch conversation comments from issues endpoint
        conv = await self.list_issue_comments(owner, name, number, page=page, per_page=per_page)
        # 2. Fetch code review comments from pulls endpoint
        url = f"/repos/{owner}/{name}/pulls/{number}/comments"
        params = {"page": page, "per_page": per_page}
        resp = await self.client.get(url, params=params)
        self._handle_response_status(resp)
        review_data = resp.json()
        if not isinstance(review_data, list):
            review_data = []
        review_sanitized = [self._sanitize_comment(it) for it in review_data]

        all_comments = conv["items"] + review_sanitized
        all_comments.sort(key=lambda c: c.get("created_at") or "")
        return {"items": all_comments, "next_page": conv.get("next_page")}

