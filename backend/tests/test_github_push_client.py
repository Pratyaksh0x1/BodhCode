import pytest
import respx

from app.github.push import (
    Conflict,
    GitHubPushClient,
    PermissionDenied,
    ValidationFailed,
    sanitize_github_message,
)


def test_sanitize_github_message() -> None:
    raw = "Invalid reference: gho_secretToken1234567890 occurred"
    sanitized = sanitize_github_message(raw)
    assert "gho_secretToken1234567890" not in sanitized


@respx.mock
@pytest.mark.asyncio
async def test_ensure_fork_with_push_permission() -> None:
    respx.get("https://api.github.com/repos/upstream/repo").respond(
        status_code=200,
        json={"name": "repo", "permissions": {"push": True}},
    )
    async with GitHubPushClient("fake-token") as client:
        owner, name = await client.ensure_fork("upstream", "repo", "myuser")
        assert (owner, name) == ("upstream", "repo")


@respx.mock
@pytest.mark.asyncio
async def test_ensure_fork_reuses_existing_fork() -> None:
    # Upstream permissions.push = False
    respx.get("https://api.github.com/repos/upstream/repo").respond(
        status_code=200,
        json={"name": "repo", "permissions": {"push": False}},
    )
    # User repo exists and is a fork
    respx.get("https://api.github.com/repos/myuser/repo").respond(
        status_code=200,
        json={"name": "repo", "fork": True},
    )
    async with GitHubPushClient("fake-token") as client:
        owner, name = await client.ensure_fork("upstream", "repo", "myuser")
        assert (owner, name) == ("myuser", "repo")


@respx.mock
@pytest.mark.asyncio
async def test_ensure_fork_creates_new_fork_and_polls() -> None:
    # Upstream permissions.push = False
    respx.get("https://api.github.com/repos/upstream/repo").respond(
        status_code=200,
        json={"name": "repo", "permissions": {"push": False}},
    )
    # User repo doesn't exist yet
    respx.get("https://api.github.com/repos/myuser/repo").respond(
        status_code=404,
    )
    # Fork creation endpoint
    respx.post("https://api.github.com/repos/upstream/repo/forks").respond(
        status_code=202,
        json={"name": "repo", "owner": {"login": "myuser"}},
    )
    # Polling fork ready check
    respx.get("https://api.github.com/repos/myuser/repo").respond(
        status_code=200,
        json={"id": 12345, "name": "repo"},
    )
    async with GitHubPushClient("fake-token") as client:
        owner, name = await client.ensure_fork("upstream", "repo", "myuser")
        assert (owner, name) == ("myuser", "repo")


@respx.mock
@pytest.mark.asyncio
async def test_git_data_creation_flow() -> None:
    async with GitHubPushClient("token-xyz") as client:
        # 1. Blob creation
        respx.post("https://api.github.com/repos/user/repo/git/blobs").respond(
            status_code=201,
            json={"sha": "blobsha123"},
        )
        blob_sha = await client.create_blob("user", "repo", "hello world")
        assert blob_sha == "blobsha123"

        # 2. Tree creation with addition and deletion (sha: None)
        respx.post("https://api.github.com/repos/user/repo/git/trees").respond(
            status_code=201,
            json={"sha": "treesha456"},
        )
        entries = [
            {"path": "added.txt", "mode": "100644", "type": "blob", "sha": "blobsha123"},
            {"path": "deleted.txt", "mode": "100644", "type": "blob", "sha": None},
        ]
        tree_sha = await client.create_tree("user", "repo", "basetree000", entries)
        assert tree_sha == "treesha456"

        # 3. Commit creation
        respx.post("https://api.github.com/repos/user/repo/git/commits").respond(
            status_code=201,
            json={"sha": "commitsha789"},
        )
        commit_sha = await client.create_commit(
            "user", "repo", "Add added.txt and remove deleted.txt", tree_sha, ["parentsha111"]
        )
        assert commit_sha == "commitsha789"

        # 4. Create branch (idempotent test)
        respx.get("https://api.github.com/repos/user/repo/git/refs/heads/feature-x").respond(
            status_code=404,
        )
        respx.post("https://api.github.com/repos/user/repo/git/refs").respond(
            status_code=201,
            json={"ref": "refs/heads/feature-x", "object": {"sha": commit_sha}},
        )
        ref_data = await client.create_branch("user", "repo", "feature-x", commit_sha)
        assert ref_data["ref"] == "refs/heads/feature-x"

        # 5. Update ref
        respx.patch("https://api.github.com/repos/user/repo/git/refs/heads/feature-x").respond(
            status_code=200,
            json={"ref": "refs/heads/feature-x", "object": {"sha": commit_sha}},
        )
        updated = await client.update_ref("user", "repo", "feature-x", commit_sha)
        assert updated["object"]["sha"] == commit_sha


@respx.mock
@pytest.mark.asyncio
async def test_open_pull_request_idempotency() -> None:
    async with GitHubPushClient("token-xyz") as client:
        # Existing open PR check returns matching PR
        respx.get("https://api.github.com/repos/upstream/repo/pulls").respond(
            status_code=200,
            json=[{"number": 99, "html_url": "https://github.com/upstream/repo/pull/99"}],
        )
        pr_data = await client.open_pull_request(
            "upstream", "repo", "myuser:feature-x", "main", "Title", "Body"
        )
        assert pr_data["number"] == 99


@respx.mock
@pytest.mark.asyncio
async def test_push_client_error_handling() -> None:
    async with GitHubPushClient("secret-token-1234") as client:
        # Conflict 409
        respx.get("https://api.github.com/repos/u/r/git/refs/heads/br").respond(status_code=404)
        respx.post("https://api.github.com/repos/u/r/git/refs").respond(status_code=409)
        with pytest.raises(Conflict) as exc1:
            await client.create_branch("u", "r", "br", "sha")
        assert "secret-token" not in str(exc1.value)

        # Validation failed 422
        respx.get("https://api.github.com/repos/u/r/pulls").respond(status_code=200, json=[])
        respx.post("https://api.github.com/repos/u/r/pulls").respond(
            status_code=422,
            json={
                "message": "Validation Failed",
                "errors": [{"message": "Reference already exists"}],
            },
        )
        with pytest.raises(ValidationFailed) as exc2:
            await client.open_pull_request("u", "r", "head", "base", "t", "b")
        assert "Validation Failed" in str(exc2.value)
        assert "secret-token" not in str(exc2.value)

        # Permission denied 403
        respx.post("https://api.github.com/repos/u/r/issues").respond(status_code=403)
        with pytest.raises(PermissionDenied) as exc3:
            await client.create_issue("u", "r", "t", "b")
        assert "secret-token" not in str(exc3.value)
