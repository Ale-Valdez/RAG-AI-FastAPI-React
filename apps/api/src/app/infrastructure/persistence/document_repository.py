from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.documents import Document, DocumentStatus
from app.domain.tenancy import TenantId
from app.infrastructure.persistence.models import DocumentRow


class SqlAlchemyDocumentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, document: Document) -> None:
        self._session.add(
            DocumentRow(
                id=document.id,
                tenant_id=document.tenant_id.value,
                filename=document.filename,
                status=document.status.value,
                created_at=datetime.now(UTC),
            )
        )

    def list_for_tenant(self, tenant_id: TenantId) -> list[Document]:
        rows = self._session.scalars(
            select(DocumentRow)
            .where(DocumentRow.tenant_id == tenant_id.value)
            .order_by(DocumentRow.created_at.desc(), DocumentRow.id.desc())
        ).all()
        return [self._to_domain(row) for row in rows]

    @staticmethod
    def _to_domain(row: DocumentRow) -> Document:
        return Document(
            id=row.id,
            tenant_id=TenantId(row.tenant_id),
            filename=row.filename,
            status=DocumentStatus(row.status),
        )
