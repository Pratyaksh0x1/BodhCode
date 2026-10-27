"""Custom exceptions for file operations in BodhCode."""


class FileServiceError(Exception):
    """Base exception for file service errors."""


class InvalidPath(FileServiceError):
    """Raised when a file path violates POSIX, security, or length rules."""


class FileNotFound(FileServiceError):
    """Raised when a requested file does not exist or has been deleted."""


class FileTooLarge(FileServiceError):
    """Raised when a file exceeds the 1 MB editable size threshold."""


class BinaryFileNotSupported(FileServiceError):
    """Raised when attempting to edit a binary file or file containing null bytes."""


class PreconditionFailed(FileServiceError):
    """Raised when an If-Match header does not match the current effective content hash."""


class RepoFilesUnavailable(FileServiceError):
    """Raised when a repository's extracted source files are not available on disk."""
