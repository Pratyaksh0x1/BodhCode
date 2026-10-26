import io
import zipfile
from pathlib import Path

import pytest

from app.github.extract import (
    TooManyFilesError,
    ZipBombError,
    extract_repo_archive,
)
from app.github.limits import MAX_FILE_BYTES


def create_test_zip(entries: dict[str, bytes | tuple[bytes, int]]) -> bytes:
    """Helper to construct in-memory zip bytes with custom entries and attrs."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            if isinstance(data, tuple):
                content, attr = data
                zi = zipfile.ZipInfo(name)
                zi.external_attr = attr
                zf.writestr(zi, content)
            else:
                zf.writestr(name, data)
    return buf.getvalue()


def test_safe_extraction_happy_path(tmp_path: Path):
    zip_bytes = create_test_zip(
        {
            "owner-repo-sha/src/index.ts": b"export const a = 1;",
            "owner-repo-sha/src/utils.tsx": b"export const B = () => null;",
            "owner-repo-sha/package.json": b'{"name": "test"}',
            "owner-repo-sha/tsconfig.json": b"{}",
            "owner-repo-sha/README.md": b"# Hello World",
            "owner-repo-sha/image.png": b"\x89PNGdisallowed",
            "owner-repo-sha/node_modules/lib/index.js": b"console.log('ignored')",
            "owner-repo-sha/.git/config": b"ignored",
        }
    )

    zip_file = tmp_path / "test.zip"
    zip_file.write_bytes(zip_bytes)

    target_dir = tmp_path / "extracted"
    count = extract_repo_archive(zip_file, target_dir)

    assert count == 5
    assert (target_dir / "src/index.ts").exists()
    assert (target_dir / "src/utils.tsx").exists()
    assert (target_dir / "package.json").exists()
    assert (target_dir / "tsconfig.json").exists()
    assert (target_dir / "README.md").exists()

    # Disallowed files and folders must NOT be extracted
    assert not (target_dir / "image.png").exists()
    assert not (target_dir / "node_modules").exists()
    assert not (target_dir / ".git").exists()


def test_reject_path_traversal_and_absolute_paths(tmp_path: Path):
    zip_bytes = create_test_zip(
        {
            "owner-repo-sha/../evil.txt": b"hacked",
            "owner-repo-sha/sub/../../escape.js": b"hacked",
            "/absolute_evil.js": b"hacked",
            "owner-repo-sha/valid.ts": b"console.log('valid');",
        }
    )

    zip_file = tmp_path / "traversal.zip"
    zip_file.write_bytes(zip_bytes)

    target_dir = tmp_path / "extracted"
    count = extract_repo_archive(zip_file, target_dir)

    assert count == 1
    assert (target_dir / "valid.ts").exists()
    assert not (tmp_path / "evil.txt").exists()
    assert not (tmp_path / "escape.js").exists()
    assert not (target_dir.parent / "evil.txt").exists()


def test_reject_symlink_entry(tmp_path: Path):
    # external_attr: 0o120777 << 16 represents a symlink in Unix
    symlink_attr = 0o120777 << 16
    zip_bytes = create_test_zip(
        {
            "owner-repo-sha/symlink.ts": (b"/etc/passwd", symlink_attr),
            "owner-repo-sha/normal.ts": b"export const x = 10;",
        }
    )

    zip_file = tmp_path / "symlink.zip"
    zip_file.write_bytes(zip_bytes)

    target_dir = tmp_path / "extracted"
    count = extract_repo_archive(zip_file, target_dir)

    assert count == 1
    assert (target_dir / "normal.ts").exists()
    assert not (target_dir / "symlink.ts").exists()


def test_skip_files_exceeding_max_file_bytes(tmp_path: Path):
    large_bytes = b"x" * (MAX_FILE_BYTES + 100)
    zip_bytes = create_test_zip(
        {
            "owner-repo-sha/large.ts": large_bytes,
            "owner-repo-sha/normal.ts": b"console.log(1)",
        }
    )

    zip_file = tmp_path / "large.zip"
    zip_file.write_bytes(zip_bytes)

    target_dir = tmp_path / "extracted"
    count = extract_repo_archive(zip_file, target_dir)

    assert count == 1
    assert not (target_dir / "large.ts").exists()
    assert (target_dir / "normal.ts").exists()


def test_zip_bomb_guard_raises(tmp_path: Path, monkeypatch):
    # Lower uncompressed limit for testing
    import app.github.extract as extract_mod

    monkeypatch.setattr(extract_mod, "MAX_UNCOMPRESSED_BYTES", 500)

    zip_bytes = create_test_zip(
        {
            "owner-repo-sha/file1.ts": b"a" * 300,
            "owner-repo-sha/file2.ts": b"b" * 300,
        }
    )

    zip_file = tmp_path / "bomb.zip"
    zip_file.write_bytes(zip_bytes)

    target_dir = tmp_path / "extracted"
    with pytest.raises(ZipBombError):
        extract_repo_archive(zip_file, target_dir)


def test_too_many_files_guard_raises(tmp_path: Path, monkeypatch):
    import app.github.extract as extract_mod

    monkeypatch.setattr(extract_mod, "MAX_SOURCE_FILES", 3)

    zip_bytes = create_test_zip(
        {f"owner-repo-sha/file{i}.ts": b"export const x = 1;" for i in range(5)}
    )

    zip_file = tmp_path / "many.zip"
    zip_file.write_bytes(zip_bytes)

    target_dir = tmp_path / "extracted"
    with pytest.raises(TooManyFilesError):
        extract_repo_archive(zip_file, target_dir)
