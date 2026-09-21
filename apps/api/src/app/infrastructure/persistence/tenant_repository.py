from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.tenancy import Tenant, TenantId
from app.infrastructure.persistence.models import TenantRow


class SqlAlchemyTenantRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, tenant: Tenant) -> None:
        self._session.add(TenantRow(id=tenant.id.value, name=tenant.name))

    def get_by_id(self, tenant_id: TenantId) -> Tenant | None:
        row = self._session.get(TenantRow, tenant_id.value)
        if row is None:
            return None
        return Tenant(id=TenantId(row.id), name=row.name)

    def any_exist(self) -> bool:
        return self._session.scalar(select(TenantRow.id).limit(1)) is not None
