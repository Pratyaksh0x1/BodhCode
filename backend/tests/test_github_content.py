"""Tests for GitHub client content endpoints using respx mocks."""

import httpx
import pytest
import respx

from app.github.client import GitHubClient


@pytest.mark.asyncio
@respx.mock
async def test_get_readme_raw():
    respx.get("https://api.github.com/repos/testowner/testrepo/readme").mock(
        return_value=httpx.Response(
            200,
            text="# Project Readme\n\nHello world",
            headers={
                "content-type": "application/vnd.github.raw+json",
                "content-disposition": 'attachment; filename="README.ja.md"',
            },
        )
    )

    async with GitHubClient("mock_token") as client:
        readme = await client.get_readme("testowner", "testrepo")
        assert readme["file_name"] == "README.ja.md"
        assert "# Project Readme" in readme["content"]


@pytest.mark.asyncio
@respx.mock
async def test_list_issues_filters_out_pull_requests():
    # GitHub returns both issues and PRs in /issues endpoint
    mock_payload = [
        {
            "number": 1,
            "title": "A real issue",
            "body": "Issue description",
            "state": "open",
            "user": {"login": "alice", "avatar_url": "https://avatars.com/u/1"},
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "labels": [{"name": "bug", "color": "d73a4a"}],
            "comments": 3,
            "html_url": "https://github.com/testowner/testrepo/issues/1",
        },
        {
            "number": 2,
            "title": "A pull request masquerading as issue",
            "body": "PR description",
            "state": "open",
            "pull_request": {"url": "https://api.github.com/repos/testowner/testrepo/pulls/2"},
            "user": {"login": "bob", "avatar_url": "https://avatars.com/u/2"},
            "created_at": "2026-01-02T00:00:00Z",
            "updated_at": "2026-01-02T00:00:00Z",
            "labels": [],
            "comments": 1,
            "html_url": "https://github.com/testowner/testrepo/pull/2",
        },
    ]

    respx.get("https://api.github.com/repos/testowner/testrepo/issues").mock(
        return_value=httpx.Response(
            200,
            json=mock_payload,
            headers={"link": '<https://api.github.com/...page=2>; rel="next"'},
        )
    )

    async with GitHubClient("mock_token") as client:
        result = await client.list_issues("testowner", "testrepo")
        items = result["items"]
        # PR #2 must be filtered out
        assert len(items) == 1
        assert items[0]["number"] == 1
        assert items[0]["title"] == "A real issue"
        assert items[0]["author"]["login"] == "alice"
        assert result["next_page"] == 2


@pytest.mark.asyncio
@respx.mock
async def test_get_issue_and_comments():
    respx.get("https://api.github.com/repos/testowner/testrepo/issues/10").mock(
        return_value=httpx.Response(
            200,
            json={
                "number": 10,
                "title": "Issue ten",
                "body": "Body ten",
                "state": "closed",
                "user": {"login": "carol", "avatar_url": "https://avatars.com/u/3"},
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-02T00:00:00Z",
                "labels": [],
                "comments": 2,
                "html_url": "https://github.com/testowner/testrepo/issues/10",
            },
        )
    )
    respx.get("https://api.github.com/repos/testowner/testrepo/issues/10/comments").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": 101,
                    "body": "First comment",
                    "user": {"login": "dave", "avatar_url": "https://avatars.com/u/4"},
                    "created_at": "2026-01-01T01:00:00Z",
                    "updated_at": "2026-01-01T01:00:00Z",
                    "html_url": "https://github.com/testowner/testrepo/issues/10#c101",
                }
            ],
        )
    )

    async with GitHubClient("mock_token") as client:
        issue = await client.get_issue("testowner", "testrepo", 10)
        assert issue["number"] == 10
        assert issue["state"] == "closed"

        comments = await client.list_issue_comments("testowner", "testrepo", 10)
        assert len(comments["items"]) == 1
        assert comments["items"][0]["author"]["login"] == "dave"


@pytest.mark.asyncio
@respx.mock
async def test_list_and_get_pulls():
    respx.get("https://api.github.com/repos/testowner/testrepo/pulls").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "number": 5,
                    "title": "PR five",
                    "body": "PR description",
                    "state": "open",
                    "user": {"login": "eve", "avatar_url": "https://avatars.com/u/5"},
                    "created_at": "2026-01-05T00:00:00Z",
                    "updated_at": "2026-01-05T00:00:00Z",
                    "labels": [],
                    "comments": 0,
                    "html_url": "https://github.com/testowner/testrepo/pull/5",
                }
            ],
        )
    )

    async with GitHubClient("mock_token") as client:
        pulls = await client.list_pulls("testowner", "testrepo")
        assert len(pulls["items"]) == 1
        assert pulls["items"][0]["number"] == 5
