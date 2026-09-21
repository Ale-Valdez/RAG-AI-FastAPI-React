class DomainError(Exception):
    """Base error for business-rule violations."""


class TenantIsolationError(DomainError):
    """Raised when a resource is accessed from another tenant."""


class NotFoundError(DomainError):
    """Raised when a requested resource does not exist."""


class UnauthenticatedError(DomainError):
    """Raised when authentication is missing or invalid."""


class InvalidDocumentTransition(DomainError):
    """Raised when a document status change is not allowed."""
