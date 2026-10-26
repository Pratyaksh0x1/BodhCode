from pathlib import Path

import pytest
import respx

from app.github.client import (
    GitHubClient,
    RateLimited,
    RepoNotFound,
    RepoTooLarge,
    TokenInvalid,
)


@pytest.mark.asyncio
async def test_get_repo_success():
    async with respx.mock(base_url="https://api.github.com") as respx_mock:
        respx_mock.get("/repos/facebook/react").respond(
            200,
            json={"default_branch": "main", "size": 1500, "private": False},
        )

        async with GitHubClient("test_token") as client:
            repo = await client.get_repo("facebook", "react")
            assert repo["default_branch"] == "main"
            assert repo["size"] == 1500
            assert repo["private"] is False


@pytest.mark.asyncio
async def test_get_repo_not_found_raises():
    async with respx.mock(base_url="https://api.github.com") as respx_mock:
        respx_mock.get("/repos/private/secret").respond(404)

        async with GitHubClient("test_token") as client:
            with pytest.raises(RepoNotFound) as exc_info:
                await client.get_repo("private", "secret")
            assert "only public repos are supported" in str(exc_info.value)


@pytest.mark.asyncio
async def test_token_invalid_raises():
    async with respx.mock(base_url="https://api.github.com") as respx_mock:
        respx_mock.get("/repos/facebook/react").respond(401)

        async with GitHubClient("bad_token") as client:
            with pytest.raises(TokenInvalid):
                await client.get_repo("facebook", "react")


@pytest.mark.asyncio
async def test_rate_limited_raises():
    async with respx.mock(base_url="https://api.github.com") as respx_mock:
        respx_mock.get("/repos/facebook/react").respond(
            403,
            headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1793000000"},
        )

        async with GitHubClient("test_token") as client:
            with pytest.raises(RateLimited) as exc_info:
                await client.get_repo("facebook", "react")
            assert "1793000000" in str(exc_info.value)


@pytest.mark.asyncio
async def test_download_zipball_streams_and_aborts_oversized(tmp_path: Path):
    dest = tmp_path / "repo.zip"
    async with respx.mock(base_url="https://api.github.com") as respx_mock:
        # Return 200 with 10 KB of data
        chunk = b"x" * 1024
        respx_mock.get("/repos/owner/repo/zipball/sha123").respond(
            200,
            content=chunk * 10,
        )

        async with GitHubClient("test_token") as client:
            # Set max_bytes to 5 KB so it triggers RepoTooLarge midway
            with pytest.raises(RepoTooLarge):
                await client.download_zipball("owner", "repo", "sha123", dest, max_bytes=5 * 1024)

        # Dest path must be deleted immediately
        assert not dest.exists()


@pytest.mark.asyncio
async def test_download_zipball_success(tmp_path: Path):
    dest = tmp_path / "valid_repo.zip"
    content = b"PK\x03\x04valid-zipball-bytes"
    async with respx.mock(base_url="https://api.github.com") as respx_mock:
        respx_mock.get("/repos/owner/repo/zipball/sha123").respond(200, content=content)

        async with GitHubClient("test_token") as client:
            bytes_written = await client.download_zipball("owner", "repo", "sha123", dest)
            assert bytes_written == len(content)
            assert dest.exists()
            assert dest.read_bytes() == content
