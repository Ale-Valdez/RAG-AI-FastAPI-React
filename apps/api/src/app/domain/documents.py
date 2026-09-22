from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.domain.errors import InvalidDocumentTransition
from app.domain.tenancy import TenantId


class DocumentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


@dataclass
class Document:
    id: str
    tenant_id: TenantId
    filename: str
    status: DocumentStatus = DocumentStatus.PENDING

    def mark_pending(self) -> None:
        if self.status not in (DocumentStatus.READY, DocumentStatus.FAILED):
            raise InvalidDocumentTransition(
                f"cannot move document from {self.status.value} to pending"
            )
        self.status = DocumentStatus.PENDING

    def mark_processing(self) -> None:
        self._require(DocumentStatus.PENDING, "processing")
        self.status = DocumentStatus.PROCESSING

    def mark_ready(self) -> None:
        self._require(DocumentStatus.PROCESSING, "ready")
        self.status = DocumentStatus.READY

    def mark_failed(self) -> None:
        self._require(DocumentStatus.PROCESSING, "failed")
        self.status = DocumentStatus.FAILED

    def _require(self, expected: DocumentStatus, target: str) -> None:
        if self.status is not expected:
            raise InvalidDocumentTransition(
                f"cannot move document from {self.status.value} to {target}"
            )
