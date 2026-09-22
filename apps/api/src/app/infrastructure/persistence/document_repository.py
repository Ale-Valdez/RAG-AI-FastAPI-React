from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.documents import Document, DocumentStatus
from app.domain.tenancy import TenantId
from app.infrastructure.persistence.models import DocumentRow


class SqlAlchemyDocumentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, document: Document) -> None:
        existing = self._session.get(DocumentRow, document.id)
        if existing is None:
            self._session.add(
                DocumentRow(
                    id=document.id,
                    tenant_id=document.tenant_id.value,
                    filename=document.filename,
                    status=document.status.value,
                    created_at=datetime.now(UTC),
                )
            )
            return
        existing.tenant_id = document.tenant_id.value
        existing.filename = document.filename
        existing.status = document.status.value

    def get(self, document_id: str) -> Document | None:
        row = self._session.get(DocumentRow, document_id)
        return self._to_domain(row) if row is not None else None

    def delete(self, document_id: str) -> None:
        row = self._session.get(DocumentRow, document_id)
        if row is not None:
            self._session.delete(row)

    def list_for_tenant(self, tenant_id: TenantId) -> list[Document]:
        rows = self._session.scalars(
            select(DocumentRow)
            .where(DocumentRow.tenant_id == tenant_id.value)
            .order_by(DocumentRow.created_at.desc(), DocumentRow.id.desc())
        ).all()
        return [self._to_domain(row) for row in rows]

    def count_processing(self, tenant_id: TenantId) -> int:
        self._session.scalars(
            select(DocumentRow)
            .where(DocumentRow.tenant_id == tenant_id.value)
            .with_for_update()
        ).all()
        count = self._session.scalar(
            select(func.count())
            .select_from(DocumentRow)
            .where(
                DocumentRow.tenant_id == tenant_id.value,
                DocumentRow.status == DocumentStatus.PROCESSING.value,
            )
        )
        return int(count or 0)

    @staticmethod
    def _to_domain(row: DocumentRow) -> Document:
        return Document(
            id=row.id,
            tenant_id=TenantId(row.tenant_id),
            filename=row.filename,
            status=DocumentStatus(row.status),
        )
