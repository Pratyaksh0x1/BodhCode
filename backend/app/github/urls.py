"""GitHub repository URL parsing and validation."""

import re
from typing import NamedTuple
from urllib.parse import urlparse

GITHUB_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
ALLOWED_HOSTS = frozenset({"github.com", "www.github.com"})
ALLOWED_SUBPATHS = frozenset(
    {"tree", "blob", "issues", "pull", "pulls", "releases", "actions", "commits", "wiki"}
)


class RepoRef(NamedTuple):
    owner: str
    name: str
    ref: str | None = None


class InvalidRepoUrl(ValueError):
    """Raised when repository URL or shorthand fails validation."""

    pass


def parse_repo_url(text: str) -> RepoRef:
    """Parse and validate a GitHub repository URL or shorthand.

    Accepts:
      - https://github.com/owner/name
      - http://github.com/owner/name
      - www.github.com/owner/name
      - github.com/owner/name
      - with .git suffix, trailing slashes
      - /tree/<branch> or /tree/<branch>/sub/dir
      - /blob/<branch>/...
      - Shorthand 'owner/name'

    Rejects:
      - Any non-github.com hosts
      - Unicode lookalike domain attacks
      - Invalid owner or repository names
      - Malformed or unsupported subpaths
    """
    if not text or not text.strip():
        raise InvalidRepoUrl("Repository URL cannot be empty.")

    raw = text.strip()

    # Check for shorthand "owner/name" (without schemes or hostnames)
    if "://" not in raw and not raw.startswith("www.") and not raw.startswith("github.com"):
        parts = [p for p in raw.split("/") if p]
        if len(parts) == 2:
            owner, name = parts[0], parts[1]
            if name.endswith(".git"):
                name = name[:-4]
            if not GITHUB_NAME_PATTERN.match(owner) or not GITHUB_NAME_PATTERN.match(name):
                raise InvalidRepoUrl(
                    "Invalid GitHub repository format: owner and name must contain only "
                    "alphanumeric characters, hyphens, periods, or underscores."
                )
            if owner in (".", "..") or name in (".", ".."):
                raise InvalidRepoUrl("Invalid repository name.")
            return RepoRef(owner=owner, name=name, ref=None)
        elif len(parts) == 1 or len(parts) > 2:
            raise InvalidRepoUrl("Invalid repository shorthand. Expected format: 'owner/repo'.")

    # Normalize protocol for URL parser
    if not raw.startswith("http://") and not raw.startswith("https://"):
        raw = f"https://{raw}"

    try:
        parsed = urlparse(raw)
    except Exception as err:
        raise InvalidRepoUrl(f"Malformed URL: {err}") from err

    hostname = parsed.hostname
    if not hostname:
        raise InvalidRepoUrl("Invalid URL: missing hostname.")

    # Guard against Unicode lookalike domain spoofing
    try:
        ascii_host = hostname.encode("ascii").decode("ascii").lower()
    except UnicodeEncodeError as err:
        raise InvalidRepoUrl(
            f"Invalid hostname '{hostname}': non-ASCII domain characters are not permitted."
        ) from err

    if ascii_host not in ALLOWED_HOSTS:
        raise InvalidRepoUrl(
            f"Only public GitHub repositories on github.com are supported. Received '{hostname}'."
        )

    path_segments = [seg for seg in parsed.path.split("/") if seg]
    if len(path_segments) < 2:
        raise InvalidRepoUrl(
            "GitHub URL must contain both an owner and a repository name (e.g. 'https://github.com/owner/repo')."
        )

    owner = path_segments[0]
    name = path_segments[1]
    if name.endswith(".git"):
        name = name[:-4]

    if not GITHUB_NAME_PATTERN.match(owner) or not GITHUB_NAME_PATTERN.match(name):
        raise InvalidRepoUrl(
            "Invalid repository name or owner: must contain only alphanumeric "
            "characters, hyphens, periods, or underscores (max 100 characters)."
        )
    if owner in (".", "..") or name in (".", ".."):
        raise InvalidRepoUrl("Invalid repository name.")

    ref: str | None = None
    if len(path_segments) > 2:
        action = path_segments[2].lower()
        if action not in ALLOWED_SUBPATHS:
            raise InvalidRepoUrl(f"Unsupported GitHub URL path: '/{action}'.")
        if action in ("tree", "blob") and len(path_segments) > 3:
            ref = path_segments[3]

    return RepoRef(owner=owner, name=name, ref=ref)
