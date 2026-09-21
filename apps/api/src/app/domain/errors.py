class DomainError(Exception):
    """Base error for business-rule violations."""


class TenantIsolationError(DomainError):
    """Raised when a resource is accessed from another tenant."""


class InvalidDocumentTransition(DomainError):
    """Raised when a document status change is not allowed."""
