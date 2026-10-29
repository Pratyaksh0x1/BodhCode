"""Unit tests for file service path normalization, working copies, and isolation."""

import os
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.config import get_settings
from app.files.errors import (
    BinaryFileNotSupported,
    FileNotFound,
    FileTooLarge,
    InvalidPath,
    PreconditionFailed,
)
from app.files.service import (
    delete_file,
    diff_for,
    list_tree,
    normalize_path,
    read_effective,
    read_original,
    rename_file,
    revert_file,
    write_file,
)
from app.github.limits import INGEST_VERSION
from app.models.files import WorkingFile
from app.models.repo import Repo
from app.models.user import User


@pytest.mark.parametrize(
    ("raw_path", "expected"),
    [
        ("src/index.ts", "src/index.ts"),
        ("src/components/Button.tsx", "src/components/Button.tsx"),
        ("./src/index.ts", "src/index.ts"),
        ("src//index.ts", "src/index.ts"),
        ("package.json", "package.json"),
    ],
)
def test_normalize_path_valid(raw_path: str, expected: str) -> None:
    assert normalize_path(raw_path) == expected


@pytest.mark.parametrize(
    "invalid_path",
    [
        "../etc/passwd",
        "src/../../etc/passwd",
        "/src/index.ts",
        "src\\index.ts",
        ".git/config",
        "src/.git/HEAD",
        "src/file\x00.ts",
        "",
        "   ",
        "a" * 301,
    ],
)
def test_normalize_path_invalid(invalid_path: str) -> None:
    with pytest.raises(InvalidPath):
        normalize_path(invalid_path)


@pytest.fixture(name="test_user")
def test_user_fixture(db_session: Session) -> User:
    from app.auth.crypto import encrypt_token

    user = User(
        login="testdev",
        avatar_url="https://github.com/testdev.png",
        email="dev@example.com",
        github_id=98765,
        encrypted_github_token=encrypt_token("gho_dummy_test_token"),
        preferred_language="en",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(name="test_repo_env")
def test_repo_env_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    monkeypatch.setattr(get_settings(), "DATA_DIR", str(tmp_path))
    owner = "octocat"
    name = "hello-world"
    commit_sha = "abc123456"

    src_dir = tmp_path / "repos" / owner / name / commit_sha / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / ".ingest_version").write_bytes(str(INGEST_VERSION).encode("utf-8"))
    (src_dir / "index.ts").write_bytes(b"console.log('hello world');\n")
    (src_dir / "utils.ts").write_bytes(b"export const add = (a, b) => a + b;\n")

    return tmp_path, commit_sha


def test_read_write_revert_round_trip(
    db_session: Session,
    test_user: User,
    test_repo_env: tuple[Path, str],
) -> None:
    _, commit_sha = test_repo_env
    repo = Repo(
        user_id=test_user.id,  # type: ignore[arg-type]
        owner="octocat",
        name="hello-world",
        branch="main",
        commit_sha=commit_sha,
        status="ready",
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    # 1. Read original
    eff = read_effective(test_user, repo, "index.ts", db_session)
    assert eff["status"] == "unchanged"
    assert eff["content"] == "console.log('hello world');\n"

    # 2. Write modification
    new_content = "console.log('modified');\n"
    res = write_file(test_user, repo, "index.ts", new_content, db_session)
    assert res["status"] == "modified"

    eff_mod = read_effective(test_user, repo, "index.ts", db_session)
    assert eff_mod["status"] == "modified"
    assert eff_mod["content"] == new_content

    # Original on disk unchanged
    assert read_original(repo, "index.ts") == "console.log('hello world');\n"

    # 3. Revert
    reverted = revert_file(test_user, repo, "index.ts", db_session)
    assert reverted is True

    eff_rev = read_effective(test_user, repo, "index.ts", db_session)
    assert eff_rev["status"] == "unchanged"
    assert eff_rev["content"] == "console.log('hello world');\n"


def test_no_op_edit_removes_working_row(
    db_session: Session,
    test_user: User,
    test_repo_env: tuple[Path, str],
) -> None:
    _, commit_sha = test_repo_env
    repo = Repo(
        user_id=test_user.id,  # type: ignore[arg-type]
        owner="octocat",
        name="hello-world",
        branch="main",
        commit_sha=commit_sha,
        status="ready",
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    # Edit file
    orig = "console.log('hello world');\n"
    write_file(test_user, repo, "index.ts", "console.log('changed');\n", db_session)

    # Verify row exists
    rows = db_session.exec(
        select(WorkingFile).where(
            WorkingFile.user_id == test_user.id,
            WorkingFile.repo_id == repo.id,
        )
    ).all()
    assert len(rows) == 1

    # Edit back to original content
    res = write_file(test_user, repo, "index.ts", orig, db_session)
    assert res["status"] == "unchanged"

    # Working row must be removed
    rows_after = db_session.exec(
        select(WorkingFile).where(
            WorkingFile.user_id == test_user.id,
            WorkingFile.repo_id == repo.id,
        )
    ).all()
    assert len(rows_after) == 0


def test_binary_and_oversize_rejected(
    db_session: Session,
    test_user: User,
    test_repo_env: tuple[Path, str],
) -> None:
    _, commit_sha = test_repo_env
    repo = Repo(
        user_id=test_user.id,  # type: ignore[arg-type]
        owner="octocat",
        name="hello-world",
        branch="main",
        commit_sha=commit_sha,
        status="ready",
    )
    db_session.add(repo)
    db_session.commit()

    # Reject null byte in content
    with pytest.raises(BinaryFileNotSupported):
        write_file(test_user, repo, "file.ts", "hello\x00world", db_session)

    # Reject > 1,000,000 bytes
    oversize = "a" * 1_000_001
    with pytest.raises(FileTooLarge):
        write_file(test_user, repo, "file.ts", oversize, db_session)


def test_deleted_file_404_on_read(
    db_session: Session,
    test_user: User,
    test_repo_env: tuple[Path, str],
) -> None:
    _, commit_sha = test_repo_env
    repo = Repo(
        user_id=test_user.id,  # type: ignore[arg-type]
        owner="octocat",
        name="hello-world",
        branch="main",
        commit_sha=commit_sha,
        status="ready",
    )
    db_session.add(repo)
    db_session.commit()

    # Delete index.ts
    delete_file(test_user, repo, "index.ts", db_session)

    # Reading effective should raise FileNotFound
    with pytest.raises(FileNotFound):
        read_effective(test_user, repo, "index.ts", db_session)

    # Revert restores it
    revert_file(test_user, repo, "index.ts", db_session)
    eff = read_effective(test_user, repo, "index.ts", db_session)
    assert eff["status"] == "unchanged"


def test_if_match_precondition(
    db_session: Session,
    test_user: User,
    test_repo_env: tuple[Path, str],
) -> None:
    _, commit_sha = test_repo_env
    repo = Repo(
        user_id=test_user.id,  # type: ignore[arg-type]
        owner="octocat",
        name="hello-world",
        branch="main",
        commit_sha=commit_sha,
        status="ready",
    )
    db_session.add(repo)
    db_session.commit()

    # Get current hash
    eff = read_effective(test_user, repo, "index.ts", db_session)
    valid_hash = eff["hash"]

    # Fails with wrong hash
    with pytest.raises(PreconditionFailed):
        write_file(
            test_user,
            repo,
            "index.ts",
            "new",
            db_session,
            if_match="wronghash123",
        )

    # Succeeds with matching hash
    write_file(
        test_user,
        repo,
        "index.ts",
        "new",
        db_session,
        if_match=valid_hash,
    )


def test_user_ownership_isolation(
    db_session: Session,
    test_user: User,
    test_repo_env: tuple[Path, str],
) -> None:
    _, commit_sha = test_repo_env
    repo = Repo(
        user_id=test_user.id,  # type: ignore[arg-type]
        owner="octocat",
        name="hello-world",
        branch="main",
        commit_sha=commit_sha,
        status="ready",
    )
    db_session.add(repo)

    user_b = User(
        github_id=99999,
        login="userb",
        name="User B",
        avatar_url="https://avatar.url/b",
        encrypted_github_token="dummy",
    )
    db_session.add(user_b)
    db_session.commit()

    # User A edits index.ts
    write_file(test_user, repo, "index.ts", "user A edit", db_session)

    # User B reads index.ts -> sees original file, not User A's edit
    eff_b = read_effective(user_b, repo, "index.ts", db_session)
    assert eff_b["status"] == "unchanged"
    assert eff_b["content"] == "console.log('hello world');\n"


def test_list_tree_and_diff(
    db_session: Session,
    test_user: User,
    test_repo_env: tuple[Path, str],
) -> None:
    _, commit_sha = test_repo_env
    repo = Repo(
        user_id=test_user.id,  # type: ignore[arg-type]
        owner="octocat",
        name="hello-world",
        branch="main",
        commit_sha=commit_sha,
        status="ready",
    )
    db_session.add(repo)
    db_session.commit()

    # Initial tree: index.ts, utils.ts
    tree1 = list_tree(test_user, repo, db_session)
    paths1 = [t["path"] for t in tree1]
    assert "index.ts" in paths1
    assert "utils.ts" in paths1

    # Add new file
    write_file(test_user, repo, "src/new.ts", "export const x = 1;", db_session)
    # Modify index.ts
    write_file(test_user, repo, "index.ts", "console.log('mod');", db_session)
    # Delete utils.ts
    delete_file(test_user, repo, "utils.ts", db_session)

    tree2 = list_tree(test_user, repo, db_session)
    status_by_path = {t["path"]: t["status"] for t in tree2}

    assert status_by_path["index.ts"] == "modified"
    assert status_by_path["src/new.ts"] == "added"
    assert status_by_path["utils.ts"] == "deleted"

    # Diff checks
    diff_mod = diff_for(test_user, repo, "index.ts", db_session)
    assert diff_mod["status"] == "modified"
    assert "hello world" in diff_mod["original"]
    assert "mod" in diff_mod["modified"]

    diff_add = diff_for(test_user, repo, "src/new.ts", db_session)
    assert diff_add["status"] == "added"
    assert diff_add["original"] == ""
    assert diff_add["modified"] == "export const x = 1;"

    diff_del = diff_for(test_user, repo, "utils.ts", db_session)
    assert diff_del["status"] == "deleted"
    assert "add = (a, b)" in diff_del["original"]
    assert diff_del["modified"] == ""


def test_rename_file(
    db_session: Session,
    test_user: User,
    test_repo_env: tuple[Path, str],
) -> None:
    _, commit_sha = test_repo_env
    repo = Repo(
        user_id=test_user.id,  # type: ignore[arg-type]
        owner="octocat",
        name="hello-world",
        branch="main",
        commit_sha=commit_sha,
        status="ready",
    )
    db_session.add(repo)
    db_session.commit()

    rename_file(test_user, repo, "index.ts", "main.ts", db_session)

    # index.ts is now deleted
    diff_old = diff_for(test_user, repo, "index.ts", db_session)
    assert diff_old["status"] == "deleted"

    # main.ts is added with original content
    diff_new = diff_for(test_user, repo, "main.ts", db_session)
    assert diff_new["status"] == "added"
    assert diff_new["modified"] == "console.log('hello world');\n"


def test_containment_blocks_symlink(
    db_session: Session,
    test_user: User,
    test_repo_env: tuple[Path, str],
) -> None:
    tmp_path, commit_sha = test_repo_env
    repo = Repo(
        user_id=test_user.id,  # type: ignore[arg-type]
        owner="octocat",
        name="hello-world",
        branch="main",
        commit_sha=commit_sha,
        status="ready",
    )
    db_session.add(repo)
    db_session.commit()

    # Create secret file outside repo dir
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("SUPER_SECRET_TOKEN", encoding="utf-8")

    src_dir = tmp_path / "repos" / "octocat" / "hello-world" / commit_sha / "src"
    symlink_path = src_dir / "evil_symlink.ts"

    try:
        os.symlink(secret_file, symlink_path)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation not supported in this test environment")

    # Accessing evil_symlink.ts should raise InvalidPath due to containment check
    with pytest.raises(InvalidPath):
        read_original(repo, "evil_symlink.ts")
