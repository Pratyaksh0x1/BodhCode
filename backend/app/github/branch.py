"""Pure branch name validation for repository branches."""

import re

BRANCH_REGEX = re.compile(r"^[A-Za-z0-9._/-]{1,100}$")

PROTECTED_BRANCH_NAMES: frozenset[str] = frozenset(
    {"main", "master", "head", "default", "release", "develop"}
)


class InvalidBranchNameError(ValueError):
    """Raised when a proposed git branch name violates security or git ref rules."""

    pass


def validate_branch_name(branch: str) -> str:
    """Validate and normalize a proposed git branch name.

    Returns the clean branch name or raises InvalidBranchNameError.
    """
    cleaned = branch.strip()

    if not cleaned:
        raise InvalidBranchNameError("Branch name cannot be empty.")

    if not BRANCH_REGEX.match(cleaned):
        raise InvalidBranchNameError(
            "Branch name must be between 1 and 100 characters and contain only "
            "alphanumeric characters, dots, underscores, dashes, or slashes."
        )

    if ".." in cleaned:
        raise InvalidBranchNameError("Branch name cannot contain consecutive dots ('..').")

    if cleaned.startswith(("-", "/")):
        raise InvalidBranchNameError("Branch name cannot start with a dash or slash.")

    if cleaned.endswith(("/", ".lock")):
        raise InvalidBranchNameError("Branch name cannot end with a slash or '.lock'.")

    if cleaned.lower() in PROTECTED_BRANCH_NAMES:
        raise InvalidBranchNameError(
            f"'{cleaned}' is a protected branch name. "
            "Please choose a descriptive feature branch name."
        )

    return cleaned
