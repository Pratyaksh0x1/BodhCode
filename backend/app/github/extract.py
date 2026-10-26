"""Safe archive extraction for untrusted repository zip archives."""

import shutil
import zipfile
from pathlib import Path

from app.github.limits import (
    EXCLUDED_DIRECTORIES,
    MAX_FILE_BYTES,
    MAX_SOURCE_FILES,
    MAX_UNCOMPRESSED_BYTES,
    is_allowed_file,
)


class ExtractionError(Exception):
    """Base exception for archive extraction failures."""

    pass


class ZipBombError(ExtractionError):
    """Raised when extracted bytes exceed safety threshold."""

    pass


class TooManyFilesError(ExtractionError):
    """Raised when extracted source files count exceeds limit."""

    pass


def extract_repo_archive(zip_path: Path, target_dir: Path) -> int:
    """Safely extract allowed source files from a repository zip archive.

    Guarantees:
      - Strips GitHub's top-level container directory.
      - Rejects path traversal attempts (.. segments, absolute paths, backslashes).
      - Rejects symlink entries to prevent filesystem escapes.
      - Enforces uncompressed byte ceiling (Zip-bomb guard).
      - Retains only allowed JavaScript/TypeScript source and config files.
      - Rejects files over MAX_FILE_BYTES.
      - Excludes common build and dependency folders (node_modules, dist, etc.).
      - Raises TooManyFilesError if source files exceed MAX_SOURCE_FILES.
      - Returns the total count of successfully extracted files.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    resolved_target = target_dir.resolve()

    total_uncompressed = 0
    extracted_files_count = 0

    with zipfile.ZipFile(zip_path, "r") as archive:
        infolist = archive.infolist()
        if not infolist:
            return 0

        # Detect top-level folder prefix added by GitHub (e.g. 'owner-name-sha/')
        valid_entries = [m.filename for m in infolist if not m.filename.startswith("/")]
        top_prefix = ""
        if valid_entries:
            candidate = valid_entries[0].split("/")[0] + "/"
            if (
                candidate != "/"
                and sum(1 for e in valid_entries if e.startswith(candidate))
                >= len(valid_entries) * 0.5
            ):
                top_prefix = candidate

        for member in infolist:
            raw_name = member.filename

            # 1. Reject symlinks: check Unix file mode bits in external_attr (0o120000 = S_IFLNK)
            unix_mode = (member.external_attr >> 16) & 0o170000
            if unix_mode == 0o120000:
                continue

            # 2. Reject malicious path characters
            if "\x00" in raw_name or "\\" in raw_name:
                continue

            # 3. Strip GitHub's top-level wrapper folder
            if top_prefix and raw_name.startswith(top_prefix):
                rel_path_str = raw_name[len(top_prefix) :]
            else:
                rel_path_str = raw_name

            # Reject leading slashes (absolute paths)
            if rel_path_str.startswith("/"):
                continue

            # Split path into segments and validate
            segments = [seg for seg in rel_path_str.split("/") if seg]
            if not segments:
                continue

            # Reject any directory traversal segments
            if any(seg in (".", "..") for seg in segments):
                continue

            # Check if directory itself
            if member.is_dir() or raw_name.endswith("/"):
                continue

            # Exclude ignored directories anywhere in parent hierarchy
            parent_dirs = segments[:-1]
            if any(p.lower() in EXCLUDED_DIRECTORIES for p in parent_dirs):
                continue

            filename = segments[-1]

            # 4. Filter allowed file types
            if not is_allowed_file(filename):
                continue

            # 5. Skip individual files exceeding per-file size cap
            if member.file_size > MAX_FILE_BYTES:
                continue

            # 6. Zip-bomb guard
            total_uncompressed += member.file_size
            if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
                raise ZipBombError(
                    f"Archive uncompressed size exceeded limit of {MAX_UNCOMPRESSED_BYTES} bytes"
                )

            # 7. Path resolution and containment check
            destination = (resolved_target / Path(*segments)).resolve()
            try:
                destination.relative_to(resolved_target)
            except ValueError:
                # Path escapes target extraction directory
                continue

            # 8. Check source file count limit
            extracted_files_count += 1
            if extracted_files_count > MAX_SOURCE_FILES:
                raise TooManyFilesError(
                    f"Repository exceeds maximum source file count limit of {MAX_SOURCE_FILES}"
                )

            # Write file safely
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source_stream, open(destination, "wb") as dest_stream:
                shutil.copyfileobj(source_stream, dest_stream)

    return extracted_files_count
