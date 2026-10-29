from datetime import UTC, datetime

import pytest
import respx
from sqlmodel import Session

from app.auth.crypto import encrypt_token
from app.auth.deps import get_current_user
from app.models.files import WorkingFile
from app.models.push import ActionLog
from app.models.repo import Repo
from app.models.user import User

CSRF_HEADERS = {"X-Requested-With": "bodhcode"}


@pytest.fixture
def auth_user(db_session: Session) -> User:
    user = User(
        github_id=12345,
        login="octocoder",
        avatar_url="https://avatar.test/octocoder",
        encrypted_github_token=encrypt_token("gho_live_oauth_token"),
        token_scopes="read:user,user:email,public_repo",
        preferred_language="en",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_repo(db_session: Session, auth_user: User) -> Repo:
    repo = Repo(
        user_id=auth_user.id,
        owner="octocoder",
        name="testrepo",
        branch="main",
        commit_sha="commitsha000111222333444555666777888999aa",
        status="ready",
        push_language_override=None,
        source_language="en",
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)
    return repo


def test_push_preview_scope_required(client, db_session: Session, test_repo: Repo) -> None:
    now = datetime.now(UTC)
    unscoped_user = User(
        github_id=54321,
        login="unscoped",
        avatar_url="",
        encrypted_github_token=encrypt_token("gho_unscoped"),
        token_scopes="read:user,user:email",
        created_at=now,
        last_login_at=now,
    )
    db_session.add(unscoped_user)
    db_session.commit()
    db_session.refresh(unscoped_user)

    client.app.dependency_overrides[get_current_user] = lambda: unscoped_user
    try:
        resp = client.post(
            f"/repos/{test_repo.id}/push/preview",
            json={
                "branch_name": "feature-x",
                "commit_message": "Add feature",
                "pr_title": "Feature X",
                "pr_body": "Details",
            },
            headers=CSRF_HEADERS,
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "scope_required"
        assert resp.json()["needed"] == "public_repo"
    finally:
        client.app.dependency_overrides.clear()


def test_push_preview_empty_changes(client, auth_user: User, test_repo: Repo) -> None:
    client.app.dependency_overrides[get_current_user] = lambda: auth_user
    try:
        resp = client.post(
            f"/repos/{test_repo.id}/push/preview",
            json={
                "branch_name": "feature-x",
                "commit_message": "Add feature",
                "pr_title": "Feature X",
                "pr_body": "Details",
            },
            headers=CSRF_HEADERS,
        )
        assert resp.status_code == 400
        assert "No changes to push" in resp.json()["detail"]
    finally:
        client.app.dependency_overrides.clear()


def test_push_preview_invalid_branch_name(
    client, db_session: Session, auth_user: User, test_repo: Repo
) -> None:
    client.app.dependency_overrides[get_current_user] = lambda: auth_user
    # Add a working file
    wf = WorkingFile(
        user_id=auth_user.id,
        repo_id=test_repo.id,
        path="src/index.ts",
        content="console.log('hi');",
        is_new=True,
    )
    db_session.add(wf)
    db_session.commit()

    try:
        # Protected name 'main'
        resp1 = client.post(
            f"/repos/{test_repo.id}/push/preview",
            json={
                "branch_name": "main",
                "commit_message": "Add feature",
                "pr_title": "Feature X",
                "pr_body": "Details",
            },
            headers=CSRF_HEADERS,
        )
        assert resp1.status_code == 400
        assert "protected branch name" in resp1.json()["detail"]

        # Traversal name '../x'
        resp2 = client.post(
            f"/repos/{test_repo.id}/push/preview",
            json={
                "branch_name": "../x",
                "commit_message": "Add feature",
                "pr_title": "Feature X",
                "pr_body": "Details",
            },
            headers=CSRF_HEADERS,
        )
        assert resp2.status_code == 400
    finally:
        client.app.dependency_overrides.clear()


def test_push_preview_blocked_by_secret(
    client, db_session: Session, auth_user: User, test_repo: Repo
) -> None:
    client.app.dependency_overrides[get_current_user] = lambda: auth_user
    wf = WorkingFile(
        user_id=auth_user.id,
        repo_id=test_repo.id,
        path="config.ts",
        content="const key = 'api_key = abcdef1234567890abcdef';",
        is_new=True,
    )
    db_session.add(wf)
    db_session.commit()

    try:
        resp = client.post(
            f"/repos/{test_repo.id}/push/preview",
            json={
                "branch_name": "fix-config",
                "commit_message": "Fix config",
                "pr_title": "Config",
                "pr_body": "Details",
            },
            headers=CSRF_HEADERS,
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["detail"]["error"] == "secret_detected"
        assert "abcdef1234567890abcdef" not in str(data)
        assert any(f["path"] == "config.ts" for f in data["detail"]["findings"])
    finally:
        client.app.dependency_overrides.clear()


def test_push_preview_blocked_by_workflow(
    client, db_session: Session, auth_user: User, test_repo: Repo
) -> None:
    client.app.dependency_overrides[get_current_user] = lambda: auth_user
    wf = WorkingFile(
        user_id=auth_user.id,
        repo_id=test_repo.id,
        path=".github/workflows/ci.yml",
        content="name: CI\non: push",
        is_new=True,
    )
    db_session.add(wf)
    db_session.commit()

    try:
        resp = client.post(
            f"/repos/{test_repo.id}/push/preview",
            json={
                "branch_name": "add-ci",
                "commit_message": "Add CI",
                "pr_title": "CI",
                "pr_body": "Details",
            },
            headers=CSRF_HEADERS,
        )
        assert resp.status_code == 400
        assert "workflow files require additional permissions" in resp.json()["detail"]
    finally:
        client.app.dependency_overrides.clear()


@respx.mock
def test_push_preview_edit_and_confirm_flow(
    client, db_session: Session, auth_user: User, test_repo: Repo
) -> None:
    client.app.dependency_overrides[get_current_user] = lambda: auth_user

    wf1 = WorkingFile(
        user_id=auth_user.id,
        repo_id=test_repo.id,
        path="src/app.ts",
        content="export const app = 1;",
        is_new=True,
    )
    wf2 = WorkingFile(
        user_id=auth_user.id,
        repo_id=test_repo.id,
        path="old_file.ts",
        content="",
        is_new=False,
        is_deleted=True,
    )
    db_session.add(wf1)
    db_session.add(wf2)
    db_session.commit()

    # Upstream check for preview will_fork calculation
    respx.get(f"https://api.github.com/repos/{test_repo.owner}/{test_repo.name}").respond(
        status_code=200,
        json={"name": test_repo.name, "permissions": {"push": True}},
    )

    try:
        # 1. Create preview
        preview_resp = client.post(
            f"/repos/{test_repo.id}/push/preview",
            json={
                "branch_name": "feat-app",
                "commit_message": "Add app",
                "pr_title": "PR App",
                "pr_body": "Body details",
                "language_override": "en",
            },
            headers=CSRF_HEADERS,
        )
        assert preview_resp.status_code == 200
        preview_data = preview_resp.json()
        preview_id = preview_data["preview_id"]
        assert len(preview_data["changes"]) == 2

        # 2. Edit preview
        edit_resp = client.post(
            f"/repos/{test_repo.id}/push/preview/{preview_id}/edit",
            json={
                "commit_message": "Add app (edited)",
                "pr_title": "PR App (edited)",
            },
            headers=CSRF_HEADERS,
        )
        assert edit_resp.status_code == 200
        assert edit_resp.json()["texts"]["commit_message"]["translated"] == "Add app (edited)"

        # 3. Confirm push with mocked Git Data API
        # Live scope check
        respx.get("https://api.github.com/user").respond(
            status_code=200,
            headers={"x-oauth-scopes": "read:user, public_repo"},
            json={"login": auth_user.login},
        )
        # Base commit query
        respx.get(
            f"https://api.github.com/repos/{test_repo.owner}/{test_repo.name}/git/commits/{test_repo.commit_sha}"
        ).respond(
            status_code=200,
            json={"tree": {"sha": "basetreesha999"}},
        )
        # Blob creation
        respx.post(
            f"https://api.github.com/repos/{test_repo.owner}/{test_repo.name}/git/blobs"
        ).respond(
            status_code=201,
            json={"sha": "blob111"},
        )
        # Tree creation
        respx.post(
            f"https://api.github.com/repos/{test_repo.owner}/{test_repo.name}/git/trees"
        ).respond(
            status_code=201,
            json={"sha": "newtreesha222"},
        )
        # Commit creation
        respx.post(
            f"https://api.github.com/repos/{test_repo.owner}/{test_repo.name}/git/commits"
        ).respond(
            status_code=201,
            json={"sha": "newcommitsha333"},
        )
        # Ref check & creation
        respx.get(
            f"https://api.github.com/repos/{test_repo.owner}/{test_repo.name}/git/refs/heads/feat-app"
        ).respond(status_code=404)
        respx.post(
            f"https://api.github.com/repos/{test_repo.owner}/{test_repo.name}/git/refs"
        ).respond(
            status_code=201,
            json={"ref": "refs/heads/feat-app", "object": {"sha": "newcommitsha333"}},
        )
        respx.patch(
            f"https://api.github.com/repos/{test_repo.owner}/{test_repo.name}/git/refs/heads/feat-app"
        ).respond(
            status_code=200,
            json={"ref": "refs/heads/feat-app", "object": {"sha": "newcommitsha333"}},
        )
        # Pull request check & creation
        respx.get(f"https://api.github.com/repos/{test_repo.owner}/{test_repo.name}/pulls").respond(
            status_code=200,
            json=[],
        )
        respx.post(
            f"https://api.github.com/repos/{test_repo.owner}/{test_repo.name}/pulls"
        ).respond(
            status_code=201,
            json={
                "html_url": "https://github.com/octocoder/testrepo/pull/1",
                "number": 1,
            },
        )

        confirm_resp = client.post(
            f"/repos/{test_repo.id}/push",
            json={"preview_id": preview_id, "confirm": True},
            headers=CSRF_HEADERS,
        )
        assert confirm_resp.status_code == 200
        assert confirm_resp.json()["pr_url"] == "https://github.com/octocoder/testrepo/pull/1"
        assert confirm_resp.json()["commit_sha"] == "newcommitsha333"

        # 4. Double submit should fail with 409
        confirm_again = client.post(
            f"/repos/{test_repo.id}/push",
            json={"preview_id": preview_id, "confirm": True},
            headers=CSRF_HEADERS,
        )
        assert confirm_again.status_code == 409
        assert "already been confirmed" in confirm_again.json()["detail"]

    finally:
        client.app.dependency_overrides.clear()


@respx.mock
def test_confirm_push_working_copy_modified_fails(
    client, db_session: Session, auth_user: User, test_repo: Repo
) -> None:
    client.app.dependency_overrides[get_current_user] = lambda: auth_user

    wf = WorkingFile(
        user_id=auth_user.id,
        repo_id=test_repo.id,
        path="src/main.ts",
        content="const v = 1;",
        is_new=True,
    )
    db_session.add(wf)
    db_session.commit()

    respx.get("https://api.github.com/user").respond(
        status_code=200,
        headers={"x-oauth-scopes": "public_repo"},
        json={"login": auth_user.login},
    )
    respx.get(f"https://api.github.com/repos/{test_repo.owner}/{test_repo.name}").respond(
        status_code=200,
        json={"name": test_repo.name, "permissions": {"push": True}},
    )

    try:
        preview_resp = client.post(
            f"/repos/{test_repo.id}/push/preview",
            json={
                "branch_name": "feat-v",
                "commit_message": "V1",
                "pr_title": "V1",
                "pr_body": "V1",
                "language_override": "en",
            },
            headers=CSRF_HEADERS,
        )
        preview_id = preview_resp.json()["preview_id"]

        # Modify the working file AFTER preview
        wf.content = "const v = 2; // modified"
        db_session.add(wf)
        db_session.commit()

        confirm_resp = client.post(
            f"/repos/{test_repo.id}/push",
            json={"preview_id": preview_id, "confirm": True},
            headers=CSRF_HEADERS,
        )
        assert confirm_resp.status_code == 409
        assert "changes were modified — preview again" in confirm_resp.json()["detail"]

    finally:
        client.app.dependency_overrides.clear()


def test_push_rate_limit(client, db_session: Session, auth_user: User, test_repo: Repo) -> None:
    client.app.dependency_overrides[get_current_user] = lambda: auth_user

    now = datetime.now(UTC)
    # Insert 5 succeeded push logs in last hour
    for i in range(5):
        log = ActionLog(
            user_id=auth_user.id,
            repo_id=test_repo.id,
            action="push",
            status="succeeded",
            target_url=f"https://github.com/pr/{i}",
            created_at=now,
        )
        db_session.add(log)
    db_session.commit()

    try:
        resp = client.post(
            f"/repos/{test_repo.id}/push",
            json={"preview_id": "dummy-id", "confirm": True},
            headers=CSRF_HEADERS,
        )
        assert resp.status_code == 429
        assert "Rate limit exceeded" in resp.json()["detail"]
    finally:
        client.app.dependency_overrides.clear()


@respx.mock
def test_issues_and_comments_flow(
    client, db_session: Session, auth_user: User, test_repo: Repo
) -> None:
    client.app.dependency_overrides[get_current_user] = lambda: auth_user

    try:
        # Issue Preview
        i_prev = client.post(
            f"/repos/{test_repo.id}/issues/preview",
            json={"title": "Bug found", "body": "Details about bug", "written_in": "en"},
            headers=CSRF_HEADERS,
        )
        assert i_prev.status_code == 200
        issue_prev_id = i_prev.json()["preview_id"]

        # Issue Edit
        i_edit = client.post(
            f"/repos/{test_repo.id}/issues/preview/{issue_prev_id}/edit",
            json={"title": "Critical bug found"},
            headers=CSRF_HEADERS,
        )
        assert i_edit.status_code == 200
        assert i_edit.json()["texts"]["title"]["translated"] == "Critical bug found"

        # Issue Confirm
        respx.get("https://api.github.com/user").respond(
            status_code=200,
            headers={"x-oauth-scopes": "read:user, public_repo"},
            json={"login": auth_user.login},
        )
        respx.post(
            f"https://api.github.com/repos/{test_repo.owner}/{test_repo.name}/issues"
        ).respond(
            status_code=201,
            json={"html_url": "https://github.com/octocoder/testrepo/issues/10", "number": 10},
        )
        i_confirm = client.post(
            f"/repos/{test_repo.id}/issues",
            json={"preview_id": issue_prev_id, "confirm": True},
            headers=CSRF_HEADERS,
        )
        assert i_confirm.status_code == 200
        assert i_confirm.json()["number"] == 10

        # Comment Preview
        c_prev = client.post(
            f"/repos/{test_repo.id}/issues/10/comments/preview",
            json={"body": "I am working on this.", "written_in": "en"},
            headers=CSRF_HEADERS,
        )
        assert c_prev.status_code == 200
        comment_prev_id = c_prev.json()["preview_id"]

        # Comment Confirm
        respx.post(
            f"https://api.github.com/repos/{test_repo.owner}/{test_repo.name}/issues/10/comments"
        ).respond(
            status_code=201,
            json={"html_url": "https://github.com/octocoder/testrepo/issues/10#issuecomment-1"},
        )
        c_confirm = client.post(
            f"/repos/{test_repo.id}/issues/10/comments",
            json={"preview_id": comment_prev_id, "confirm": True},
            headers=CSRF_HEADERS,
        )
        assert c_confirm.status_code == 200
        assert "issuecomment-1" in c_confirm.json()["comment_url"]

        # Activity endpoint check
        activity_resp = client.get("/user/activity", headers=CSRF_HEADERS)
        assert activity_resp.status_code == 200
        activities = activity_resp.json()
        assert len(activities) >= 2
        # Verify no token or secret in activity response
        assert "gho_" not in str(activities)

    finally:
        client.app.dependency_overrides.clear()
