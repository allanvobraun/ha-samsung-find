from __future__ import annotations


class SamsungFindError(Exception):
    """Base error for Samsung Find."""


class SamsungFindValidationError(SamsungFindError):
    """Raised when Samsung data cannot be validated."""


class SamsungFindLoginTimeout(SamsungFindError):
    """Raised when QR login does not complete before timeout."""


class SamsungFindApiError(SamsungFindError):
    """Raised when the Samsung API returns an unexpected response."""

    def __init__(self, message: str, *, status: int | None = None, body: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.body = body


class SamsungFindAuthError(SamsungFindApiError):
    """Raised when the Samsung session is not valid anymore."""
